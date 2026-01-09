from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from ada_backend.database.models import EnvType, EvaluationType, VersionOutput
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.quality_assurance_repository import (
    create_datasets,
    create_inputs_groundtruths,
)
from ada_backend.schemas.input_groundtruth_schema import InputGroundtruthCreate
from ada_backend.schemas.llm_judges_schema import LLMJudgeCreate, LLMJudgeUpdate
from ada_backend.schemas.project_schema import ProjectCreateSchema
from ada_backend.schemas.qa_evaluation_schema import BooleanEvaluationResult, ErrorEvaluationResult
from ada_backend.services.errors import LLMJudgeNotFound
from ada_backend.services.project_service import create_workflow, delete_project_service, get_project_service
from ada_backend.services.qa.llm_judges_service import (
    create_llm_judge_service,
    delete_llm_judges_service,
    get_llm_judges_by_project_service,
    update_llm_judge_service,
)
from ada_backend.services.qa.qa_evaluation_service import (
    delete_judge_evaluations_service,
    get_evaluations_by_version_output_service,
    run_judge_evaluation_service,
)

ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")

MOCK_LLM_SERVICE_PATH = (
    "ada_backend.services.qa.qa_evaluation_service.CompletionService.constrained_complete_with_pydantic_async"
)


def _create_project_and_graph_runner(session) -> tuple[UUID, UUID]:
    project_id = uuid4()
    user_id = uuid4()
    project_payload = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"qa_evaluation_test_{project_id}",
        description="Test project for QA evaluation",
    )
    create_workflow(
        session=session,
        user_id=user_id,
        organization_id=ORGANIZATION_ID,
        project_schema=project_payload,
    )

    project_details = get_project_service(session, project_id)
    draft_graph_runner_id = next(gr.graph_runner_id for gr in project_details.graph_runners if gr.env == EnvType.DRAFT)
    return project_id, draft_graph_runner_id


def _create_evaluation_scenario(session, project_id: UUID, graph_runner_id: UUID) -> dict:
    datasets = create_datasets(
        session=session,
        project_id=project_id,
        dataset_names=["test_dataset"],
    )

    inputs_groundtruths = create_inputs_groundtruths(
        session=session,
        dataset_id=datasets[0].id,
        inputs_groundtruths_data=[
            InputGroundtruthCreate(
                input={"messages": [{"role": "user", "content": "What is 2 + 2?"}]},
                groundtruth="4",
            )
        ],
    )

    version_output = VersionOutput(
        input_id=inputs_groundtruths[0].id,
        graph_runner_id=graph_runner_id,
        output='{"messages": [{"role": "assistant", "content": "4"}]}',
    )
    session.add(version_output)

    judge = create_llm_judge_service(
        session=session,
        project_id=project_id,
        judge_data=LLMJudgeCreate(
            name="Test Judge",
            evaluation_type=EvaluationType.BOOLEAN,
            prompt_template="Test prompt template",
        ),
    )

    return {
        "project_id": project_id,
        "version_output_id": version_output.id,
        "judge_id": judge.id,
    }


def test_llm_judge_management():
    """Test complete LLM judge CRUD operations."""
    with get_db_session() as session:
        project_id, _ = _create_project_and_graph_runner(session)

        judges = get_llm_judges_by_project_service(session=session, project_id=project_id)
        assert judges == []

        create_data = LLMJudgeCreate(
            name="Test Judge",
            description="Test description",
            evaluation_type=EvaluationType.BOOLEAN,
            prompt_template="Test: {{input}}",
        )
        judge = create_llm_judge_service(
            session=session,
            project_id=project_id,
            judge_data=create_data,
        )
        assert judge.name == "Test Judge"
        judge_id = judge.id

        judges = get_llm_judges_by_project_service(session=session, project_id=project_id)
        assert len(judges) == 1
        assert judges[0].id == judge_id
        assert judges[0].name == "Test Judge"
        assert judges[0].project_id == project_id

        update_data = LLMJudgeUpdate(name="Updated Judge Name", description="Updated description", temperature=0.9)
        updated_judge = update_llm_judge_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            judge_data=update_data,
        )
        assert updated_judge.name == "Updated Judge Name"
        assert updated_judge.description == "Updated description"
        assert updated_judge.temperature == 0.9
        assert updated_judge.id == judge_id

        delete_llm_judges_service(
            session=session,
            project_id=project_id,
            judge_ids=[judge_id],
        )

        update_data = LLMJudgeUpdate(name="Update on unexisting judge")
        with pytest.raises(LLMJudgeNotFound):
            update_llm_judge_service(
                session=session,
                project_id=project_id,
                judge_id=judge_id,
                judge_data=update_data,
            )

        delete_project_service(session=session, project_id=project_id)


@patch(MOCK_LLM_SERVICE_PATH)
@pytest.mark.asyncio
async def test_run_delete_evaluation_boolean(mock_llm):
    mock_llm.return_value = BooleanEvaluationResult(result=True, justification="Test justification")
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_graph_runner(session)
        evaluation_scenario = _create_evaluation_scenario(session, project_id, graph_runner_id)

        version_output_id = evaluation_scenario["version_output_id"]
        judge_id = evaluation_scenario["judge_id"]

        evaluation = await run_judge_evaluation_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            version_output_id=version_output_id,
        )

        assert evaluation.judge_id == judge_id
        assert evaluation.version_output_id == version_output_id
        assert evaluation.evaluation_result.type == "boolean"
        assert evaluation.evaluation_result.justification == "Test justification"

        delete_judge_evaluations_service(session=session, evaluation_ids=[evaluation.id])

        delete_judge_evaluations_service(session=session, evaluation_ids=[evaluation.id])  # idempotent

        evaluations = get_evaluations_by_version_output_service(
            session=session,
            version_output_id=version_output_id,
        )
        assert evaluations == []

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_evaluation_errors():
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_graph_runner(session)
        evaluation_scenario = _create_evaluation_scenario(session, project_id, graph_runner_id)

        version_output_id = evaluation_scenario["version_output_id"]

        non_existent_judge_id = uuid4()
        with pytest.raises(ValueError, match="Failed to run judge evaluation"):
            await run_judge_evaluation_service(
                session=session,
                project_id=project_id,
                judge_id=non_existent_judge_id,
                version_output_id=version_output_id,
            )

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_validation_errors_version_output():
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_graph_runner(session)
        evaluation_scenario = _create_evaluation_scenario(session, project_id, graph_runner_id)

        non_existent_version_output_id = uuid4()
        with pytest.raises(ValueError, match="Failed to run judge evaluation"):
            await run_judge_evaluation_service(
                session=session,
                project_id=evaluation_scenario["project_id"],
                judge_id=evaluation_scenario["judge_id"],
                version_output_id=non_existent_version_output_id,
            )

        delete_project_service(session=session, project_id=evaluation_scenario["project_id"])


@pytest.mark.asyncio
async def test_version_output_empty_error():
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_graph_runner(session)
        evaluation_scenario = _create_evaluation_scenario(session, project_id, graph_runner_id)

        version_output_id = evaluation_scenario["version_output_id"]
        judge_id = evaluation_scenario["judge_id"]

        version_output = session.query(VersionOutput).filter(VersionOutput.id == version_output_id).first()
        version_output.output = ""
        session.flush()

        evaluation = await run_judge_evaluation_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            version_output_id=version_output_id,
        )

        assert evaluation.evaluation_result.type == "error"
        assert isinstance(evaluation.evaluation_result, ErrorEvaluationResult)
        assert "no output" in evaluation.evaluation_result.justification.lower()

        delete_project_service(session=session, project_id=project_id)
