# Agentic Toolbox

## Set up

### Installations

To install the other packages, you need to use Poetry and use conda environment.
You can follow this [tutorial](https://www.anaconda.com/download) to install anaconda.
Once you have installed anaconda, create a conda environment in the folder of the code.
It should always be named 'venv_poetry_chatbot'.
To create this environment and add it in your folder, use the following command:

```
conda create -p ./venv_poetry_chatbot python=3.10
```

Once it is created, activate it:

```
source activate ./venv_poetry_chatbot
```

You can then install poetry by doing

```
pip install poetry
```

By using poetry, you can select the packages you want to install.
To make things easier, a script can be run and will parse you chatbot-config.yaml
file that contains the specifications of your bot, and will install the correct dependancies.
To configure the chatbot-config.yaml, you can check the appropriate section below.
Once your chatbot configuration is done:

- Run the bash script

```
./install_poetry.sh
```
To run the bash script, you need to install yq if you don't already have it: `brew install yq`

If you want to install all dependancies, run the command:

```
poetry install 
```

You should run all commands in this enviromnent.

### Makefile Commands (shortcuts)

Here is a list of the commands available in the Makefile and what they do:

- `run-slack`: This command runs the chatbot as a Slack app. It uses the `__main__` part of the `slack_bot.py` script.

- `run-terminal`: This command runs the chatbot as a terminal app. It uses the `main.py` script with the `--mode terminal --trace` options.

- `build-vectorstore`: This command builds the vector store. It runs the `build_vectorstore.py` script.

- `copy-config-files`: This command copies example configuration files to their actual locations. It copies `chatbot-config_example.yaml` to `chatbot-config.yaml`, `knowledge_base_config_example.yaml` to `knowledge_base_config.yaml`, and `company_context_example.yaml` to `company_context.yaml`.

- `test`: This command runs the tests with coverage. It uses the `pytest` module with the coverage option.

- `format`: This command formats the code using Black.

- `quality-check`: This command checks the code quality using flake8 and Black. It first runs flake8 for linting, then runs Black in check mode to ensure the code is properly formatted.

- `pre-push`: This command runs tests and quality checks before pushing code. It simulates what the CI does. If both pass, it prints "All checks passed. Ready to push."

To use these commands, type `make <command>` in your terminal. For example, to run the chatbot as a Slack app, you would type `make run-slack`.

##### How is the install_poetry.sh working?

In the install_poetry.sh file, a dictionary contains the matching between the
name of the tool available in the chatbot-config.yaml file and the appropriate packages in the pyproject.toml
file. If you want to add a tool and the appropriate packages, you need to edit the pyproject.toml file
and the install_poetry.sh file.

#### Troubleshooting

If you get an error when you are trying to install `onnxruntime==1.17.0`, you can install the package using conda :

```
conda install onnxruntime -c conda-forge
```

NB : If you use a micro AWS instance, you will need to increase tmp memory :

```
sudo mount -o remount,size=10G /tmp
```

You might, as well, have a gcc error when installing ghdbscan. Install it with the following command :

```
sudo yum install gcc
```

### Credentials

You need to create a file named `credentials.env` in the root folder of the project like this :
Make sure that you have a credentials JSON file for accessing your Google Drive

- [Check this link to create a google_api_credentials.json file](https://developers.google.com/drive/api/quickstart/python)
- Place the `google_api_credentials.json` file in the root of the project
- Set up the path inside the `credentials.env`

```
OPENAI_API_KEY=sk-xxxxxx
MISTRAL_API_KEY=xxxxxx
SLACK_BOT_TOKEN=xxxxxx
SLACK_APP_TOKEN=xxxxxx
NOTION_INTEGRATION_TOKEN=xxxxxx
COHERE_API_KEY=xxxxxx
GOOGLE_DRIVE_CREDENTIALS_PATH="google_api_credentials.json"
#SNOWFLAKE
SNOWFLAKE_PASSWORD = xxxx
SNOWFLAKE_ACCOUNT = xxxx
SNOWFLAKE_USER = xxxx
#QDRANT
QDRANT_CLUSTER_URL = xxxxx
QDRANT_API_KEY = xxxxx
```

You can copy the template file `credentials.env.example` and replace the values.

### Knowledge base configuration

To set up the knowledge base, you need to create a file named `knowledge_base_config.yaml` in the root folder of the project. You can use the template file `knowledge_base_config_example.yaml` as a reference and replace the placeholder values with your own. Certain variables in the configuration file are already set to default values, and you only need to modify specific ones according to your requirements.

### Company context

To set up the company context, you need to create a file named `company_context.yaml` in the root folder of the project. You can use the template file `company_context_example.yaml` as a reference and replace the placeholder values with your own.

### Chatbot configuration

To set up the chatbot, you need to create a file named `chatbot-config.yaml` in the root folder of the project. You can use the template file `chatbot-config_example.yaml` as a reference and replace the placeholder values with your own.

### Google Drive Setup (TODO: to update to the new world ingestion !)

- Define the `folder_path` within the configuration
- Define the `azure_analysis_result_path` folder path where you want to save Azure analysis results. You have two options:

1. **Google Drive Folder Path**: Specify a path if you want to save the results to Google Drive.
2. **Local Folder Path**: Alternatively, define a local path if you prefer to save the results locally.

**Note**: If you do not define the azure_analysis_result_path folder, each azure JSON file will be saved in the same folder as the original document file.

```
sources:
  - name: "GoogleDriveRetriever"
    kb_config:
      <<: *knowledge_manager_defaults
      chroma_collection_name: "google_drive"
    load_config:
      folders_paths:
        - "https://drive.google.com/drive/folders/folder_id"
      azure_analysis_result_path: "local_folder_path/local_subfolder_path/" or "https://drive.google.com/drive/folders/folder_id"
```

### Notion Set Up

See the knowledge_base_config_example.yaml file

WARNING! For now, there is a discrepancy with the chromadb for the notion as Notion is not updated at the same time as the Notion documentation (not the same client). That is why when updating each night, we need to relaunch the bot, thus stopping for a short time the service

### Slack Set Up

By default the slack loader load all the channel : in the `knowledge_base_config.yml`, the parameters `channels_ids` is set to `None`.

If you want to load only specific channels, you will need to set this parameters in the yaml file. For example (the channels ids are fake) :

```
sources:
  - name: "SlackRetriever"
    config:
      <<: *knowledge_manager_defaults
      chroma_collection_name: "slack"
      channels_ids : 
        - channel_id_1, 
        - channel_id_2
```

**How to found the channel id of a Channel in Slack ?**

1. Click on the name of the channel
2. The channel id is at the end of the pop up window.

### Snowflake
To use snowflake, you will need to have a account.
In the `credentials.env` file, you will need to add :
```
SNOWFLAKE_PASSWORD = xxxx
SNOWFLAKE_ACCOUNT = xxxx
SNOWFLAKE_USER = xxxx
```
To get the account identifier, you must copy the account url. You get something like: 
https://xxxx.us-east-3.aws.snowflakecomputing.com. The account identifier is `xxxx.us-east-3.aws`

### Qdrant - Vectorstore
To use qdrant as your vectorstore, you will need to add in the `credentials.env` file:
```
QDRANT_CLUSTER_URL = xxxxx
QDRANT_API_KEY = xxxxx
```

## Usage

### Build the knowledge base

To build the knowledge base, we use Snowflake, Qdrant and Airbyte.

Each source has its own ingestion method. All ingestion scripts are stored in the `data_ingestion` folder.

#### Slack
1. In Airbyte, ingest raw data from Slack into Snowflake (Slack -> Snowflake)
2. To process the raw data (Snowflake -> Snowflake), run the python script : `poetry run python -m data_ingestion.slack.slack_ingest`
3. In Airbyte, update the Qdrant vectorstore (Snowflake -> Qdrant)

#### Notion
1. Notion -> Snowflake : To ingest raw data from Notion into Snowflake, run the python script : `poetry run python -m data_ingestion.notion.notion_ingestion`
2. Snowflake -> Snowflake : To process the raw data , run the python script : `poetry run python -m data_ingestion.notion.notion_processing`
3. Snowflake -> Qdrant: in Airbyte

#### Webdriver
1. Notion -> Snowflake puis **2.** Snowflake -> Snowflake : run the script : `poetry run python -m data_ingestion.ingestion_example`. In this script we do the ingestion and the processing in the same script (but it is 2 differente function). You can replace the url with your website url, you want to ingest.
3. Snowflake -> Qdrant: in Airbyte


### Run the bot

The bot can be run:

In the **Command line**:

```
poetry run python -m apps.main_agent --agent juno
```

As a **Slack bot**:

```
poetry run python -m apps.slack_bot.slack_bot
```

To use the slack bot, you need to invite the bot to a channel and then you can trigger it with `@bot_name` anywhere in the message.

## Deployment guide

To see how to deploy in a production environment, you can check this [documentation](deployment_scripts/README.md).

As a **Gradio App**:

```
poetry run python -m apps.gradio_app.run_app
```

For more information on running the Gradio app, please refer to the [Gradio App Module README](apps/gradio_app/Readme.md).

## Developper guide

### Logging convention

Logs are made with the "logging" module, a logging-config.yaml file and a python file logger.py
The config will write both on the stdout and in a file logs/server.log

#### Run the setup

At the beguinning of the entrypoint of the application, you should run the setup function from the logger.py file

```python
from logger import setup_logging

setup_logging()
```

#### Use the logger

Then, everywhere else, you can use the logger in your code

```python
import logging

LOGGER = logging.getLogger(__name__)

def some_function():
    LOGGER.info("Info message from some_function")
```

### Tracing

To know more about the tracing, you can check the [tracing documentation](engine/trace/README.md).

### Ingestion Convention

In the metadata, you will need two default metadata parameters : `title` and `url` to work with the chatbot.

## Tools

The tools are availables for the ReAct Agent. 

### Tool description

Here are the different tools : 
* Image generation tool : Generate a prompt for image genration sent to StableDiffusion API.
* News API tool : Find some articles with some keywords extracted from the user query
* SQL generation tool : Generate an SQL query based on a natural language question of the user
* SQL query tool : Generate and execute an SQL query based on a natural language question of the user
* Search API tool (Tavily Tool) : Answer a question based on sources extracted from the Internet using API search

### Tool usage 

To provide a tool to the ReAct agent you have to add the tool description and function in engine/agent/react_function_calling.py

### Search API Tool (Tavily Tool)
You will need to set your `TAVILY_API_KEY`. To get you api key, create an account on `https://tavily.com/`.

### SQL Tools

* SQL generation tool : 
You neeed to provide your database table schema. Follow the example in data_ingestion/sql/example_table_schema.json
You can provide a subset of the tables to consider with the variable INCLUDE_TABLES in engine/agent/tools/sql/sql_generation_tool_function.py

* SQL query tool : You need to provide your credentials to acces the database. Follow the exemple in data_ingestion/sql/sql_credentials.env
You can provide a subset of the tables to consider with the variable INCLUDE_TABLES in engine/agent/tools/sql/sql_generation_tool_function.py

# Usage : 
To provide a tool to the ReAct agent you have to add the tool description and function in engine/agent/react_function_calling.py

## Web Loader

By default the web loader will load all the website. If you want to load only the page url, you will need to set `website_depth=0`

### Installation

You will need to install Chrome and a chromedriver to use the web reader.
On macOs, to install the chromedriver, you can do `brew install --cask chromedriver`

On EC2 amazon Linux,

- to install Chrome, you can do :

```
wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
sudo yum localinstall google-chrome-stable_current_x86_64.rpm
google-chrome --version # to check that chrome is installed correctly
```

- to install the chromedriver, you can do :

```
CHROME_DRIVER_VERSION=$(curl -s https://chromedriver.storage.googleapis.com/LATEST_RELEASE)
wget https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/bin/chromedriver
chromedriver --version
```

- You can test the installation :

```
chromedriver --url-base=/wd/hub
```
