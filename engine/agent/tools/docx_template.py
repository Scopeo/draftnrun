import base64
import json
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type
from pydantic import BaseModel, Field, ConfigDict, create_model
from PIL import Image
import requests

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import ToolDescription, ComponentAttributes, AgentPayload, ChatMessage
from engine.llm_services.llm_service import CompletionService
from engine.temps_folder_utils import get_output_dir
from engine.trace.trace_manager import TraceManager
from engine.storage_service.s3_loader import load_file_from_s3

try:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm
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
    Concatène *tout* le texte des XML Word et supprime les tags XML,
    pour recoller les balises Jinja même si elles sont fragmentées.
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
    # indexation: item["sku"] or item['sku']
    for m in re.finditer(rf"\b{re.escape(item_var)}\s*\[\s*(['\"])(.+?)\1\s*\]", expr):
        fields.append(m.group(2))
    # dedupe
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
    """
    Télécharge une image depuis HTTPS et la sauvegarde dans un format compatible.
    Préserve le format original quand possible, convertit seulement si nécessaire.

    Args:
        img_path: URL HTTPS ou chemin local de l'image
        output_dir: Répertoire de sortie pour sauvegarder l'image

    Returns:
        Chemin local de l'image sauvegardée ou None si échec
    """
    try:
        if img_path.startswith(("http://", "https://")):
            LOGGER.info(f"Téléchargement de l'image depuis: {img_path}")
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
                    LOGGER.info(f"Image sauvegardée dans le format original {original_format}: {output_path}")
                else:
                    filename = f"image_{hash(img_path) % 100000}.png"
                    output_path = output_dir / filename

                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")

                    img.save(output_path, "PNG")
                    LOGGER.info(f"Image convertie de {original_format} vers PNG: {output_path}")

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
            info = {"item_var": item_var, "list_expr": rhs, "fields": set(), "scalar": False, "segments": 0}
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
            # si on est dans un for, accumule ce tag pour analyse du segment
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
                setattr(sub, "model_config", ConfigDict(extra="forbid"))
                setattr(sub, "__dyn_fields__", {})
                cur[k] = (sub, Field(...))
            cur = getattr(cur[k][0], "__dyn_fields__")


def _materialize(fields: Dict) -> Dict:
    concrete = {}
    for name, (tp, fi) in fields.items():
        if isinstance(tp, type) and hasattr(tp, "__dyn_fields__"):
            sub_fields = _materialize(getattr(tp, "__dyn_fields__"))
            model = create_model(tp.__name__, **sub_fields)
            setattr(model, "model_config", ConfigDict(extra="forbid"))
            concrete[name] = (model, fi)
        else:
            concrete[name] = (tp, fi)
    return concrete


def build_context_response_model(analysis: TemplateAnalysis, image_keys: List[str]) -> Type[BaseModel]:
    """
    Construit un modèle strict (tous champs requis, extra=forbid)
    - context: variables scalaires + boucles (items stricts)
    - images: un champ str requis par clé
    - racine: {context, images} tous les deux requis
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

    # 2) conditions -> bool requis
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
                cur = getattr(cur[k][0], "__dyn_fields__")
            cur[parts[-1]] = (bool, Field(...))

    for list_name, info in analysis.loops.items():
        if info.get("scalar") and not info.get("fields"):
            # boucle scalaire: pros: list[str] requis
            root_fields[list_name] = (List[str], Field(...))
        else:
            item_fields = {attr: (str, Field(...)) for attr in sorted(info.get("fields") or [])}
            ItemModel = create_model(f"{list_name.capitalize()}Item", **item_fields)
            setattr(ItemModel, "model_config", ConfigDict(extra="forbid"))
            root_fields[list_name] = (List[ItemModel], Field(...))

    ContextModel = create_model("ContextModel", **_materialize(root_fields))
    setattr(ContextModel, "model_config", ConfigDict(extra="forbid"))

    images_fields = {}
    for k in image_keys:
        ImageDataModel = create_model(
            f"{k.capitalize()}ImageData",
            path=(str, Field(..., description="Path or URL to the image")),
            size=(int, Field(..., description="Image size in millimeters")),
        )
        setattr(ImageDataModel, "model_config", ConfigDict(extra="forbid"))
        images_fields[k] = (ImageDataModel, Field(...))

    ImagesModel = create_model("ImagesModel", **images_fields)
    setattr(ImagesModel, "model_config", ConfigDict(extra="forbid"))

    DocxContextResponse = create_model(
        "DocxContextResponse",
        context=(ContextModel, Field(...)),
        images=(ImagesModel, Field(...)),
    )
    setattr(DocxContextResponse, "model_config", ConfigDict(extra="forbid"))
    return DocxContextResponse


SYSTEM = (
    "Tu renvoies UNIQUEMENT un JSON valide qui respecte strictement le schéma implicite du response_format. "
    "Pas de texte, pas de Markdown."
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
            "description": "Path to the DOCX template file (.docx) that contains Jinja2 placeholders. Either this or template_base64 or template_s3_url must be provided.",
        },
        "template_base64": {
            "type": "string",
            "description": "Base64 encoded DOCX template content. Either this or template_input_path or template_s3_url must be provided.",
        },
        "template_s3_url": {
            "type": "string",
            "description": "S3 URL of the DOCX template file (.docx). Either this or template_input_path or template_base64 must be provided.",
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


class DocxTemplateAgent(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = False

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        completion_service: CompletionService,
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

    async def _llm_generate_context(
        self,
        response_model: type[BaseModel],
        brief: str,
        examples: Optional[dict] = None,
        image_specs: dict[str, dict] = None,
    ) -> BaseModel:
        image_specs = image_specs or {}

        image_descriptions = []
        for key, spec in image_specs.items():
            size = spec.get("size", 25)
            image_descriptions.append(f"- {key}: taille {size}mm")

        user = (
            f"Brief métier:\n{brief}\n\n"
            f"Règles:\n"
            f"- Remplis toutes les clés possibles.\n"
            f"- Les listes doivent contenir ≥ 1 élément cohérent.\n"
            f"- Dates au format YYYY-MM-DD.\n"
            f"- Pour les images, fournis un objet avec 'path' et 'size':\n"
            f"  - 'path': si c'est un lien http, utilise le lien directement. Si c'est une image locale, utilise le chemin relatif.\n"
            f"  - 'size': utilise EXACTEMENT la taille spécifiée ci-dessous pour chaque image:\n"
            + "\n".join(image_descriptions)
            + "\n"
            f"N'invente pas de lien ou de chemin, utilise uniquement ceux qui existent.\n"
            f"- Réponds par un JSON qui matche le schéma attendu par le response_format."
        )
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        if examples:
            messages.append(
                {"role": "user", "content": f"Exemples (indicatifs):\n{json.dumps(examples, ensure_ascii=False)}"}
            )

        return await self._completion_service.constrained_complete_with_pydantic_async(
            messages=messages,
            response_format=response_model,
            stream=False,
        )

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        ctx: Optional[dict] = None,
        **kwargs: Any,
    ) -> AgentPayload:
        span = get_current_span()

        try:
            template_input_path = kwargs.get("template_input_path") or (ctx or {}).get("template_input_path")
            template_base64 = kwargs.get("template_base64") or (ctx or {}).get("template_base64")
            template_information_brief = kwargs.get("template_information_brief", "")
            output_filename = kwargs.get("output_filename", "")

            if not template_input_path and not template_base64:
                error_msg = "Either template_input_path, template_base64, or template_s3_url must be provided"
                LOGGER.error(error_msg)
                span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=error_msg)],
                    error=error_msg,
                    is_final=True,
                )

            template_sources = [template_input_path, template_base64]
            provided_sources = [source for source in template_sources if source is not None]
            if len(provided_sources) > 1:
                error_msg = "Only one of template_input_path, template_base64, or template_s3_url should be provided, not multiple"
                LOGGER.error(error_msg)
                span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=error_msg)],
                    error=error_msg,
                    is_final=True,
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
                    return AgentPayload(
                        messages=[ChatMessage(role="assistant", content=error_msg)],
                        error=error_msg,
                        is_final=True,
                    )

                if not template_path.suffix.lower() == ".docx":
                    error_msg = f"Template file must be a .docx file: {template_input_path}"
                    LOGGER.error(error_msg)
                    span.set_attributes({SpanAttributes.OUTPUT_VALUE: error_msg})
                    return AgentPayload(
                        messages=[ChatMessage(role="assistant", content=error_msg)],
                        error=error_msg,
                        is_final=True,
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
                    return AgentPayload(
                        messages=[ChatMessage(role="assistant", content=error_msg)],
                        error=error_msg,
                        is_final=True,
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
                    print(img_data)
                    print(key)
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

            if template_path and str(template_path).startswith(str(get_output_dir())):
                try:
                    template_path.unlink()
                    LOGGER.info(f"Cleaned up S3 downloaded template file: {template_path}")
                except Exception as e:
                    LOGGER.warning(f"Failed to clean up S3 downloaded file: {e}")

            success_msg = (
                f"Successfully analyzed template, generated content, and saved to filename: {output_filename}"
            )
            LOGGER.info(success_msg)

            template_type = "base64" if template_base64 else "input_path"

            span.set_attributes(
                {
                    SpanAttributes.INPUT_VALUE: f"template: {template_type}, brief: {template_information_brief[:100]}..., output_filename: {output_filename}",
                    SpanAttributes.OUTPUT_VALUE: success_msg,
                }
            )

            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=success_msg)],
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
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=error_msg)],
                error=error_msg,
                is_final=True,
            )
