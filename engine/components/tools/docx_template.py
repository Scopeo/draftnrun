import base64
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type

import requests
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, create_model

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.temps_folder_utils import get_output_dir
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

try:
    from docx.shared import Mm
    from docxtpl import DocxTemplate, InlineImage
except ImportError:
    DocxTemplate = None
    InlineImage = None
    Mm = None

LOGGER = logging.getLogger(__name__)

TAG_RE = re.compile(r"({%.*?%}|{{.*?}})", flags=re.S)
FOR_START_RE = re.compile(r"^{%-?\s*for\s+(.+?)\s+in\s+(.+?)\s*-?%}$", flags=re.S)
FOR_END_RE = re.compile(r"^{%-?\s*endfor\s*-?%}$", flags=re.S)
IF_START_RE = re.compile(r"^{%-?\s*if\s+(.+?)\s*-?%}$", flags=re.S)
IF_END_RE = re.compile(r"^{%-?\s*endif\s*-?%}$", flags=re.S)
VAR_TAG_RE = re.compile(r"^{{-?\s*(.+?)\s*-?}}$", flags=re.S)


def _read_docx_plaintext(docx_path: str | Path) -> str:
    """
    Concatenates *all* text from Word XML files and removes XML tags,
    to reassemble Jinja tags even if they are fragmented.
    """
    docx_path = Path(docx_path)
    buf: List[str] = []
    with zipfile.ZipFile(docx_path, "r") as z:
        for name in z.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            xml = z.read(name).decode("utf-8", errors="ignore")
            # Delete all XML tags but keep the braces
            text = re.sub(r"<[^>]+>", "", xml)
            buf.append(text)
    return "".join(buf)


def _extract_item_fields(expr: str, item_var: str) -> List[str]:
    fields: List[str] = []
    # paths by dots: item.foo, item.product.sku
    for m in re.finditer(rf"\b{re.escape(item_var)}(?:\.(?:[A-Za-z_]\w*))+", expr):
        path = m.group(0).split(".")[1:]  # remove "item"
        if path:
            fields.append(".".join(path))
    for m in re.finditer(rf"\b{re.escape(item_var)}\s*\[\s*(['\"])(.+?)\1\s*\]", expr):
        fields.append(m.group(2))

    seen = set()
    out = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _segment_uses_bare_item(expr: str, item_var: str) -> bool:
    e = expr.strip()
    while e.startswith("(") and e.endswith(")"):
        e = e[1:-1].strip()
    e = e.split("|", 1)[0].strip()  # remove filters
    return e == item_var


def _download_and_convert_image(img_path: str, output_dir: Path) -> Optional[str]:
    try:
        if img_path.startswith(("http://", "https://")):
            LOGGER.info(f"Downloading image from: {img_path}")
            response = requests.get(img_path, timeout=30)
            response.raise_for_status()

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
            temp_file.write(response.content)
            temp_file.close()

            with Image.open(temp_file.name) as img:
                original_format = img.format
                if original_format in ["JPEG", "PNG"]:
                    extension = original_format.lower()
                    if extension == "jpeg":
                        extension = "jpg"
                    filename = f"image_{hash(img_path) % 100000}.{extension}"
                    output_path = output_dir / filename

                    img.save(output_path, original_format)
                    LOGGER.info(f"Image saved in original format {original_format}: {output_path}")
                else:
                    filename = f"image_{hash(img_path) % 100000}.png"
                    output_path = output_dir / filename

                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")

                    img.save(output_path, "PNG")
                    LOGGER.info(f"Image converted from {original_format} to PNG: {output_path}")

                Path(temp_file.name).unlink()

                return str(output_path)

        else:
            img_path_obj = get_output_dir() / Path(img_path)
            if not img_path_obj.exists():
                LOGGER.warning(f"Local image not found: {img_path}")
                return None

            suffix = img_path_obj.suffix.lower()
            if suffix in [".jpg", ".jpeg", ".png"]:
                LOGGER.info(f"Local image already in a compatible format: {img_path_obj}")
                return str(img_path_obj)

            with Image.open(img_path_obj) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    filename = f"{img_path_obj.stem}.png"
                    output_path = output_dir / filename
                    img.save(output_path, "PNG")
                    LOGGER.info(f"Image with transparency converted to PNG: {output_path}")
                else:
                    filename = f"{img_path_obj.stem}.jpg"
                    output_path = output_dir / filename
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(output_path, "JPEG", quality=95)
                    LOGGER.info(f"Image converted to JPEG: {output_path}")

                return str(output_path)

    except Exception as e:
        LOGGER.error(f"Error processing image {img_path}: {e}")
        return None


class TemplateAnalysis(BaseModel):
    variables: Set[str]
    conditions: List[str]
    loops: Dict[str, Dict[str, Any]]


def analyze_docx_template(docx_path: str | Path) -> TemplateAnalysis:
    text = _read_docx_plaintext(docx_path)
    tokens = TAG_RE.findall(text)

    variables: Set[str] = set()
    conditions: List[str] = []
    loops: Dict[str, Dict[str, Any]] = {}

    stack: List[Tuple[str, Dict[str, Any]]] = []  # ("for"/"if", info)
    segs: Dict[int, List[str]] = {}

    for tok in tokens:
        # {% for ... %}
        m = FOR_START_RE.match(tok)
        if m:
            lhs, rhs = m.group(1).strip(), m.group(2).strip()
            item_var = lhs.split(",")[-1].strip()
            info = {
                "item_var": item_var,
                "list_expr": rhs,
                "fields": set(),
                "scalar": False,
                "segments": 0,
            }
            stack.append(("for", info))
            segs[id(info)] = []
            continue

        # {% endfor %}
        if FOR_END_RE.match(tok):
            while stack:
                kind, info = stack.pop()
                if kind == "for":
                    segment = "\n".join(segs.pop(id(info), []))
                    for var_expr in VAR_TAG_RE.findall(segment):
                        if _segment_uses_bare_item(var_expr, info["item_var"]):
                            info["scalar"] = True
                        else:
                            info["fields"].update(_extract_item_fields(var_expr, info["item_var"]))
                    info["segments"] += 1
                    key = info["list_expr"]
                    if key in loops:
                        loops[key]["fields"].update(info["fields"])
                        loops[key]["scalar"] = loops[key]["scalar"] or info["scalar"]
                        loops[key]["segments"] += info["segments"]
                    else:
                        loops[key] = info
                    break
            continue

        # {% if ... %}
        m = IF_START_RE.match(tok)
        if m:
            expr = m.group(1).strip()
            var = re.split(r"\s+|==|!=|>=|<=|>|<|\)|\(", expr)[0]
            if var:
                conditions.append(var)
            stack.append(("if", {"expr": expr}))
            continue

        # {% endif %}
        if IF_END_RE.match(tok):
            while stack:
                kind, _ = stack.pop()
                if kind == "if":
                    break
            continue

        # {{ ... }}
        m = VAR_TAG_RE.match(tok)
        if m:
            expr = m.group(1).strip()
            variables.add(expr)
            # if we're in a for loop, accumulate this tag for segment analysis
            for kind, info in reversed(stack):
                if kind == "for":
                    segs[id(info)].append(tok)
                    break

    return TemplateAnalysis(variables=variables, conditions=conditions, loops=loops)


def infer_image_keys(analysis: TemplateAnalysis) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for v in analysis.variables:
        if "_image" in v:
            size_match = re.search(r"_image_(\d+)$", v)
            if size_match:
                size = int(size_match.group(1))
                specs[v] = {"size": size}
            else:
                specs[v] = {"size": 25}
    return specs


def _ensure_nested_fields(root: Dict, path: List[str]) -> None:
    """
    root: dict[name] -> (type, Field)
    path: ex ['client','name'] -> client: ClientModel(name: str)
    """
    cur = root
    for i, k in enumerate(path):
        last = i == len(path) - 1
        if last:
            cur.setdefault(k, (str, Field(...)))
        else:
            if k not in cur:
                sub = create_model(k.capitalize() + "Model")
                # v2: config via 'model_config'
                sub.model_config = ConfigDict(extra="forbid")
                sub.__dyn_fields__ = {}
                cur[k] = (sub, Field(...))
            cur = cur[k][0].__dyn_fields__


def _materialize(fields: Dict) -> Dict:
    concrete = {}
    for name, (tp, fi) in fields.items():
        if isinstance(tp, type) and hasattr(tp, "__dyn_fields__"):
            sub_fields = _materialize(tp.__dyn_fields__)
            model = create_model(tp.__name__, **sub_fields)
            model.model_config = ConfigDict(extra="forbid")
            concrete[name] = (model, fi)
        else:
            concrete[name] = (tp, fi)
    return concrete


def build_context_response_model(analysis: TemplateAnalysis, image_keys: List[str]) -> Type[BaseModel]:
    """
    Builds a strict model (all fields required, extra=forbid)
    - context: scalar variables + loops (strict items)
    - images: one required str field per key
    - root: {context, images} both required
    """
    root_fields: Dict[str, tuple[type, Field]] = {}
    loop_vars = set()
    for list_name, info in analysis.loops.items():
        loop_vars.add(info.get("var", ""))

    for dotted in analysis.variables:
        if "_image" in dotted:
            continue
        if dotted in loop_vars:
            continue
        parts = [p for p in dotted.split(".") if p]
        if parts:
            _ensure_nested_fields(root_fields, parts)

    # 2) conditions -> bool required
    for cond in analysis.conditions:
        parts = [p for p in cond.split(".") if p]
        if not parts:
            continue
        if len(parts) == 1:
            root_fields.setdefault(parts[0], (bool, Field(...)))
        else:
            _ensure_nested_fields(root_fields, parts[:-1])
            cur = root_fields
            for k in parts[:-1]:
                cur = cur[k][0].__dyn_fields__
            cur[parts[-1]] = (bool, Field(...))

    for list_name, info in analysis.loops.items():
        if info.get("scalar") and not info.get("fields"):
            root_fields[list_name] = (List[str], Field(...))
        else:
            item_fields = {attr: (str, Field(...)) for attr in sorted(info.get("fields") or [])}
            ItemModel = create_model(f"{list_name.capitalize()}Item", **item_fields)
            ItemModel.model_config = ConfigDict(extra="forbid")
            root_fields[list_name] = (List[ItemModel], Field(...))

    ContextModel = create_model("ContextModel", **_materialize(root_fields))
    ContextModel.model_config = ConfigDict(extra="forbid")

    images_fields = {}
    for k in image_keys:
        ImageDataModel = create_model(
            f"{k.capitalize()}ImageData",
            path=(str, Field(..., description="Path or URL to the image")),
            size=(int, Field(..., description="Image size in millimeters")),
        )
        ImageDataModel.model_config = ConfigDict(extra="forbid")
        images_fields[k] = (ImageDataModel, Field(...))

    ImagesModel = create_model("ImagesModel", **images_fields)
    ImagesModel.model_config = ConfigDict(extra="forbid")

    DocxContextResponse = create_model(
        "DocxContextResponse",
        context=(ContextModel, Field(...)),
        images=(ImagesModel, Field(...)),
    )
    DocxContextResponse.model_config = ConfigDict(extra="forbid")
    return DocxContextResponse


SYSTEM = (
    "You return ONLY valid JSON that strictly adheres to the implicit schema of the response_format. "
    "No text, no Markdown."
)

FILL_TEMPLATE_PROMPT = (
    "Business brief:\n{brief}\n\n"
    "Rules:\n"
    "- Fill all possible keys.\n"
    "- Lists must contain ≥ 1 coherent element.\n"
    "- Dates in DD-MM-YYYY format.\n"
    "- For images, provide an object with 'path' and 'size':\n"
    "  - 'path': if it's an http link, use the link directly. "
    "If it's a local image, use the relative path.\n"
    "  - 'size': use EXACTLY the size specified below for each image:\n"
    "{image_descriptions}\n"
    "Don't invent any link or path, only use those that exist.\n"
    "- Respond with a JSON that matches the schema expected by the response_format."
)


DOCX_TEMPLATE_TOOL_DESCRIPTION = ToolDescription(
    name="docx_template",
    description=(
        "Analyze a DOCX template, generate context data using LLM based on a brief, and fill the template. "
        "Automatically analyzes Jinja2 placeholders in the template and generates appropriate content using AI. "
        "Supports both file path and base64 encoded template."
    ),
    tool_properties={
        "template_input_path": {
            "type": "string",
            "description": (
                "Path to the DOCX template file (.docx) that contains Jinja2 placeholders. "
                "Either this or template_base64 must be provided."
            ),
        },
        "template_base64": {
            "type": "string",
            "description": (
                "Base64 encoded DOCX template content. Either this or template_input_path must be provided."
            ),
        },
        "template_information_brief": {
            "type": "string",
            "description": "Business brief or context description used to generate content for the template.",
        },
        "output_filename": {
            "type": "string",
            "description": "Filename where the filled DOCX file should be saved.",
        },
    },
    required_tool_properties=["output_filename", "template_information_brief"],
)


class DocxTemplateInputs(BaseModel):
    template_input_path: Optional[str] = Field(
        default=None,
        json_schema_extra={"disabled_as_input": True},
    )
    template_information_brief: str = Field(
        description="Instructions describing what content to inject in the template placeholders.",
    )
    output_filename: str = Field(
        default="filled_template.docx",
        description="Filename for the filled DOCX file.",
    )
    model_config = {"extra": "allow"}


class DocxTemplateOutputs(BaseModel):
    output: str = Field(description="The success or error message from the DOCX template processing.")
    # TODO: Make simple docx_filename field instead of artifacts dictionary
    artifacts: dict[str, Any] = Field(description="The artifacts to be returned to the user.")
    is_final: bool = Field(default=True, description="Indicates if this is the final output of the component.")


class DocxTemplateAgent(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return DocxTemplateInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return DocxTemplateOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "template_information_brief", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        completion_service: CompletionService,
        additional_instructions: Optional[str] = None,
        template_base64: Optional[str] = None,
        tool_description: ToolDescription = DOCX_TEMPLATE_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._completion_service = completion_service
        if DocxTemplate is None:
            raise ImportError(
                "docxtpl library is required for DOCX template functionality. "
                "Install it with: pip install python-docx-template"
            )
        self.additional_instructions = additional_instructions
        self.template_base64 = template_base64

    async def _llm_generate_context(
        self,
        response_model: type[BaseModel],
        brief: str,
        image_specs: dict[str, dict] = None,
    ) -> BaseModel:
        image_specs = image_specs or {}

        image_descriptions = []
        for key, spec in image_specs.items():
            size = spec.get("size", 25)
            image_descriptions.append(f"- {key}: size {size}mm")

        image_descriptions_str = "\n".join(image_descriptions) if image_descriptions else ""
        user = FILL_TEMPLATE_PROMPT.format(
            brief=brief,
            image_descriptions=image_descriptions_str,
        )
        if self.additional_instructions:
            user += f"\n\nAdditional instructions:\n{self.additional_instructions}"
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

        return await self._completion_service.constrained_complete_with_pydantic_async(
            messages=messages,
            response_format=response_model,
            stream=False,
        )

    async def _run_without_io_trace(
        self,
        inputs: DocxTemplateInputs,
        ctx: dict,
    ) -> DocxTemplateOutputs:
        span = get_current_span()

        template_input_path = inputs.template_input_path
        template_base64 = (
            getattr(inputs, "template_base64", None) or self.template_base64 or ctx.get("template_base64")
        )
        template_information_brief = inputs.template_information_brief
        output_filename = inputs.output_filename

        try:
            if not template_input_path and not template_base64:
                error_msg = "Either template_input_path or template_base64 must be provided"
                LOGGER.error(error_msg)
                span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                return DocxTemplateOutputs(
                    output=error_msg,
                    artifacts={},
                    is_final=False,
                )

            template_sources = [template_input_path, template_base64]
            provided_sources = [source for source in template_sources if source is not None]
            if len(provided_sources) > 1:
                error_msg = "Only one of template_input_path or template_base64 should be provided, not multiple"
                LOGGER.error(error_msg)
                span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                return DocxTemplateOutputs(
                    output=error_msg,
                    artifacts={},
                    is_final=False,
                )

            output_dir = get_output_dir()
            template_path = None
            temp_template_file = None

            if template_input_path:
                template_path = output_dir / Path(template_input_path)
                if not template_path.exists():
                    error_msg = f"Template file not found: {template_input_path}"
                    LOGGER.error(error_msg)
                    span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                    return DocxTemplateOutputs(
                        output=error_msg,
                        artifacts={},
                        is_final=False,
                    )

                if not template_path.suffix.lower() == ".docx":
                    error_msg = f"Template file must be a .docx file: {template_input_path}"
                    LOGGER.error(error_msg)
                    span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                    return DocxTemplateOutputs(
                        output=error_msg,
                        artifacts={},
                        is_final=False,
                    )

            elif template_base64:
                try:
                    template_content = base64.b64decode(template_base64)

                    temp_template_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
                    temp_template_file.write(template_content)
                    temp_template_file.close()

                    template_path = Path(temp_template_file.name)
                    LOGGER.info(f"Created temporary template file from base64: {template_path}")

                except Exception as e:
                    error_msg = f"Failed to decode base64 template: {str(e)}"
                    LOGGER.error(error_msg)
                    span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                    return DocxTemplateOutputs(
                        output=error_msg,
                        artifacts={},
                        is_final=False,
                    )

            output_path = output_dir / Path(output_filename)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            LOGGER.info("Analyzing DOCX template...")
            analysis = analyze_docx_template(template_path)
            image_specs = infer_image_keys(analysis)
            image_keys = list(image_specs.keys())

            LOGGER.info("Generating context using LLM...")
            ResponseModel = build_context_response_model(analysis, image_keys)
            resp_obj = await self._llm_generate_context(
                response_model=ResponseModel,
                brief=template_information_brief,
                image_specs=image_specs,
            )
            context = resp_obj.context.model_dump()
            images = resp_obj.images.model_dump()

            LOGGER.info("Filling DOCX template...")
            template = DocxTemplate(str(template_path))
            if images:
                for key, img_data in images.items():
                    img_path = img_data["path"]
                    img_size = img_data["size"]
                    processed_img_path = _download_and_convert_image(img_path, output_dir)
                    if not processed_img_path:
                        LOGGER.warning(f"Failed to process image {img_path}, skipping...")
                        continue

                    try:
                        context[key] = InlineImage(template, processed_img_path, width=Mm(img_size))
                        LOGGER.info(f"Successfully added image {key} to template with size {img_size}mm")
                    except Exception as e:
                        LOGGER.warning(f"Failed to load image {processed_img_path}: {e}, skipping...")
                        continue

            template.render(context)
            template.save(str(output_path))

            if temp_template_file:
                try:
                    Path(temp_template_file.name).unlink()
                    LOGGER.info(f"Cleaned up temporary template file: {temp_template_file.name}")
                except Exception as e:
                    LOGGER.warning(f"Failed to clean up temporary file: {e}")

            success_msg = (
                f"Successfully analyzed template, generated content, and saved to filename: {output_filename}"
            )
            LOGGER.info(success_msg)

            template_type = "base64" if template_base64 else "input_path"

            span.set_attributes({
                SpanAttributes.INPUT_VALUE: serialize_to_json(
                    {
                        "template": template_type,
                        "brief": (
                            template_information_brief[:100]
                            if len(template_information_brief) > 100
                            else template_information_brief
                        ),
                        "output_filename": output_filename,
                    },
                    shorten_string=False,
                    indent=0,
                ),
            })

            return DocxTemplateOutputs(
                output=success_msg,
                artifacts={"docx_filename": str(output_filename)},
                is_final=True,
            )

        except Exception as e:
            error_msg = f"Error processing DOCX template: {str(e)}"
            LOGGER.exception(error_msg)
            if "temp_template_file" in locals() and temp_template_file:
                try:
                    Path(temp_template_file.name).unlink()
                except Exception:
                    pass
            span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
            return DocxTemplateOutputs(
                output=error_msg,
                artifacts={},
                is_final=False,
            )
