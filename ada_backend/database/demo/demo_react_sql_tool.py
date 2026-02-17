from uuid import UUID, uuid4

from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB
from ada_backend.schemas.pipeline.base import (
    ComponentInstanceSchema,
    PipelineParameterSchema,
)
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema
from settings import settings

ADDITIONAL_DB_DESCRIPTION = (
    "Pour les tables, voici une explication des données: \n"
    "- pour les colonnes indicateurs de nationalités, 1 : français, 2 : étranger\n"
    "- pour l'état matrimonial antérieur du conjoint, 1 : célibataire, 3 : veuf, 4 : divorcé\n"
    "- pour la tranche de commune du lieu de domicile, None: indéterminé ou pays étranger,"
    "P : commune de plus de 10 000 habitants, M : commune de moins de 10 000 habitants, "
    "A : Terres australes et antarctiques, COM non précisé\n"
    "- pour la tranche d’unité urbaine 2017, None : indéterminé, 0 : commune rurale, "
    "1 : unité urbaine de 2 000 à 4 999 habitants, "
    "2 : unité urbaine de 5 000 à 9 999 habitants, "
    "3 : unité urbaine de 10 000 à 19 999 habitants, "
    "4 : unité urbaine de 20 000 à 49 999 habitants, "
    "5 : unité urbaine de 50 000 à 99 999 habitants, "
    "6 : unité urbaine de 100 000 à 199 999 habitants, "
    "7 : unité urbaine de 200 000 à 1 999 999 habitants, 8 : agglomération de Paris, "
    "9 : COM ou étranger\n"
    "Dans la table naissance :\n"
    "- pour le sexe de l'enfant, 1 : masculin, 2 : féminin\n"
    "- pour les conditions de l'accouchement, None: jugement déclaratif de naissance, "
    "ES : dans un établissement spécialisé, AU : autre\n"
    "- pour l'année de mariage des parents, 0000 : Enfant né hors mariage ou jugement "
    "déclaratif de naissance, AAAA : année du mariage\n"
    "- Indicateur du lieu de naissance de la mère/père, 1 : née en France métropolitaine, "
    "2 : née dans un DOM, 3 : née dans un COM, 4 : née à l’étranger\n"
    "- pour l'origine du nom de l'enfant, None: Origine du nom non connue (Jugement "
    "déclaratif de naissance), 1 : Père, 2 : Mère, 3 : Père-mère, 4 : Mère-Père, 5 : Autre"
    "- pour la situation professionnelle mère/père, None: retraité ou inactif, S : salarié, "
    "NS : actif non salarié, ND : inconnue \n"
    "- pour la comparaison des dates anniversaires de mariage des parents et "
    "de naissance de l’enfant, None : né hors mariage, "
    "1 : naissance survenue avant l’anniversaire de mariage, "
    "2 : naissance survenue le même jour ou après l’anniversaire du mariage, "
    "9 : date absente (pour le jugement déclaratif de naissance, la date de mariage n’est "
    "pas demandée lorsque les parents sont mariés).\n"
    "- Durée écoulée depuis l’événement précédent, None : enfant né hors mariage, premier né "
    "ou jugement déclaratif de naissance, "
    "00 à NN : nombre d’années écoulées (depuis le mariage ou la naissance précédente)"
)


def build_react_sql_agent_chatbot(components: dict[str, UUID], graph_runner_id: UUID):
    COMPONENT_INSTANCES_IDS: dict[str, UUID] = {
        "react_sql_agent": uuid4(),
        "snowflake_service": uuid4(),
    }

    instances = [
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["react_sql_agent"],
            name="ReAct SQL Agent",
            component_id=components["react_sql_agent"],
            component_version_id=components["react_sql_agent_v2"],
            is_start_node=True,
            parameters=[
                PipelineParameterSchema(name=COMPLETION_MODEL_IN_DB, value="openai:gpt-5-mini"),
                PipelineParameterSchema(
                    name="additional_db_description",
                    value=ADDITIONAL_DB_DESCRIPTION,
                ),
                PipelineParameterSchema(
                    name="engine_url",
                    value=(
                        f"snowflake://{settings.SNOWFLAKE_USER}:{settings.SNOWFLAKE_PASSWORD}"
                        f"@{settings.SNOWFLAKE_ACCOUNT}/SCOPEO/data_gouv?warehouse=TEST_WAREHOUSE"
                        "&role=SCOPEO_READ_ROLE"
                    ),
                ),
            ],
        )
    ]
    edges = []
    return GraphUpdateSchema(component_instances=instances, relationships=[], edges=edges)
