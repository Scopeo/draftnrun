import strawberry
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from ada_backend.database.setup_db import get_db
from ada_backend.graphql.context import GraphQLContext
from ada_backend.graphql.mutations import Mutation
from ada_backend.graphql.queries import Query


async def get_context(
    request: Request,
    db: Session = Depends(get_db),
) -> GraphQLContext:
    return GraphQLContext(request=request, db=db)


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql",
)
