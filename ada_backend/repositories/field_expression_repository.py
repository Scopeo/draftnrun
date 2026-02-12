from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_field_expression(
    session: Session,
    expression_json: dict,
) -> db.FieldExpression:
    expr = db.FieldExpression(
        expression_json=expression_json,
    )
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def get_field_expression(
    session: Session,
    field_expression_id: UUID,
) -> Optional[db.FieldExpression]:
    return session.query(db.FieldExpression).filter(db.FieldExpression.id == field_expression_id).first()


def update_field_expression(
    session: Session,
    field_expression_id: UUID,
    expression_json: dict,
) -> Optional[db.FieldExpression]:
    expr = get_field_expression(session, field_expression_id)
    if not expr:
        return None

    expr.expression_json = expression_json
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def delete_field_expression_by_id(
    session: Session,
    field_expression_id: UUID,
) -> bool:
    deleted_count = session.query(db.FieldExpression).filter(db.FieldExpression.id == field_expression_id).delete()
    if deleted_count > 0:
        session.commit()
        return True
    return False


def get_input_port_dependents_referencing_instance(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
) -> list[tuple[UUID, str]]:
    """
    Return (component_instance_id, name) for input port instances in this graph whose
    field expression JSON references the given component_instance_id (as a ref node instance).

    Uses a single SQL query with jsonb_path_exists for performance.
    """
    ref_id = str(component_instance_id)
    # Recursive descent $.** finds any descendant; filter for objects with type "ref" and instance == ref_id
    path = 'strict $.** ? (@.type == "ref" && @.instance == $id)'
    rows = session.execute(
        text("""
            SELECT ipi.component_instance_id, ipi.name
            FROM input_port_instances ipi
            INNER JOIN field_expressions fe ON fe.id = ipi.field_expression_id
            INNER JOIN graph_runner_nodes grn ON grn.node_id = ipi.component_instance_id
            WHERE grn.graph_runner_id = :graph_runner_id
              AND ipi.component_instance_id != :component_instance_id
              AND ipi.field_expression_id IS NOT NULL
              AND jsonb_path_exists(
                  fe.expression_json,
                  :path::jsonpath,
                  jsonb_build_object('id', :ref_id)
              )
        """),
        {
            "graph_runner_id": graph_runner_id,
            "component_instance_id": component_instance_id,
            "path": path,
            "ref_id": ref_id,
        },
    ).fetchall()
    return [(r[0], r[1]) for r in rows]
