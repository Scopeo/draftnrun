<script setup lang="ts">
import { logger } from '@/utils/logger'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { scopeoApi } from '@/api'
import { useAbility } from '@casl/vue'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github-dark.css'
import { computed, onMounted, ref, watch, withDefaults } from 'vue'
import { useApiEnvironment } from '@/composables/useApiEnvironment'
import vHighlight from '@/directives/vHighlight'

import type {
  ApiKey,
  ApiKeysResponse,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  RevokeKeyResponse,
} from '@/types/apiKeys'

const props = withDefaults(defineProps<Props>(), {
  type: 'agent',
})

// Register languages for syntax highlighting
hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('bash', bash)

interface Props {
  projectId?: string
  projectName?: string
  type?: 'agent' | 'workflow'
  // Backward compatibility for direct agent prop
  agent?: any | null
}

const { environment } = useApiEnvironment()
const ability = useAbility()

const apiBaseUrl = import.meta.env.VITE_SCOPEO_API_URL

// Compute project ID from multiple sources for flexibility
const computedProjectId = computed(() => {
  return props.projectId || props.agent?.id || ''
})

// API/Webhook toggle
const endpointMode = ref<'api' | 'webhook'>('api')

// API Keys state
const apiKeys = ref<ApiKey[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const newKeyDialog = ref(false)
const newKeyName = ref('')
const generatedKey = ref('')

const { notify } = useNotifications()

// Refs for revoke confirmation
const showRevokeConfirmation = ref(false)
const keyToRevoke = ref<ApiKey | null>(null)

// Response example selector
const selectedResponseExample = ref<'base64' | 'url' | 'no-file'>('base64')

const apiUrl = computed(() => `${apiBaseUrl}/projects/${computedProjectId.value}/${environment.value}/run`)

const webhookUrl = computed(() => {
  const base = apiBaseUrl?.endsWith('/') ? apiBaseUrl.slice(0, -1) : apiBaseUrl
  return `${base}/webhooks/trigger/${computedProjectId.value}/envs/${environment.value}`
})

const activeUrl = computed(() => (endpointMode.value === 'api' ? apiUrl.value : webhookUrl.value))

const isDevEnvironment = computed({
  get: () => environment.value === 'draft',
  set: value => {
    environment.value = value ? 'draft' : 'production'
  },
})

// Response examples
const responseExamples = computed(() => {
  const examples = {
    base64: {
      title: 'base64',
      code: `{
  "message": "I've generated the PDF and named it document.pdf.",
  "error": null,
  "artifacts": {
    "pdf_filename": "document.pdf"
  },
  "trace_id": "0x597c478a490f618b978dc8011527c8a5",
  "files": [
    {
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "size": 5276,
      "data": "JVBERi0xLjQKJeLjz9MKMyAwIG9iago...",
      "url": null,
      "s3_key": null
    }
  ]
}`,
    },
    url: {
      title: 'url',
      code: `{
  "message": "I've generated the PDF and named it document.pdf.",
  "error": null,
  "artifacts": {
    "pdf_filename": "document.pdf"
  },
  "trace_id": "0x597c478a490f618b978dc8011527c8a5",
  "files": [
    {
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "size": 5276,
      "data": null,
      "url": "https://.../document.pdf?X-Amz...",
      "s3_key": null
    }
  ]
}`,
    },
    'no-file': {
      title: 'No file / None',
      code: `{
  "message": "I've generated the PDF and named it document.pdf.",
  "error": null,
  "artifacts": {
    "pdf_filename": "document.pdf"
  },
  "trace_id": "0x597c478a490f618b978dc8011527c8a5",
  "files": []
}`,
    },
  }

  return examples[selectedResponseExample.value]
})

const selectedLanguage = ref('python')

const apiLanguages = computed(() => {
  const currentProjectId = computedProjectId.value
  const currentEnv = environment.value
  const normalizedBaseUrl = apiBaseUrl?.endsWith('/') ? apiBaseUrl.slice(0, -1) : apiBaseUrl

  return [
    {
      title: 'Python',
      value: 'python',
      languageClass: 'language-python',
      icon: 'logos:python',
      code: `import requests

API_KEY = "your_api_key"
PROJECT_ID = "${currentProjectId}"
ENV = "${currentEnv}"
URL = f"${normalizedBaseUrl}/projects/{PROJECT_ID}/{ENV}/run"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "messages": [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you! How can I help you today?"},
        {"role": "user", "content": "What is the capital of France?"}
    ],
    "set_ids": ["defaults", "demo-custom"]
}

params = {"response_format": "base64"}

response = requests.post(URL, json=payload, headers=headers, params=params)

if response.status_code == 200:
    print("Success:", response.json())
else:
    print("Error:", response.status_code, response.text)`,
    },
    {
      title: 'JavaScript',
      value: 'javascript',
      languageClass: 'language-javascript',
      icon: 'logos:javascript',
      code: `const apiKey = "your_api_key";
const projectId = "${currentProjectId}";
const env = "${currentEnv}";
const url = \`${normalizedBaseUrl}/projects/\${projectId}/\${env}/run\`;

headers = {
    "X-API-Key": apiKey,
    "Content-Type": "application/json"
};

const payload = {
    messages: [
        { role: "user", content: "Hello, how are you?" },
        { role: "assistant", content: "I'm doing well, thank you! How can I help you today?" },
        { role: "user", content: "What is the capital of France?" }
    ],
    set_ids: ["defaults", "demo-custom"]
};

const urlWithParams = \`\${url}?response_format=base64\`;

fetch(urlWithParams, {
    method: "POST",
    headers: headers,
    body: JSON.stringify(payload)
})
.then(response => response.json())
.then(data => {
    console.log("Success:", data);
})
.catch(error => console.error("Error:", error));`,
    },
    {
      title: 'cURL',
      value: 'curl',
      languageClass: 'language-bash',
      icon: 'vscode-icons:file-type-shell',
      code: `curl -X POST "${normalizedBaseUrl}/projects/${currentProjectId}/${currentEnv}/run?response_format=base64" \\
     -H "X-API-Key: your_api_key" \\
     -H "Content-Type: application/json" \\
     -d '{
       "messages": [
         {"role": "user", "content": "Hello, how are you?"},
         {"role": "assistant", "content": "I am doing well, thank you! How can I help you today?"},
         {"role": "user", "content": "What is the capital of France?"}
       ],
       "set_ids": ["defaults", "demo-custom"]
     }'`,
    },
  ]
})

const webhookLanguages = computed(() => {
  const currentProjectId = computedProjectId.value
  const currentEnv = environment.value
  const normalizedBaseUrl = apiBaseUrl?.endsWith('/') ? apiBaseUrl.slice(0, -1) : apiBaseUrl

  return [
    {
      title: 'Python',
      value: 'python',
      languageClass: 'language-python',
      icon: 'logos:python',
      code: `import requests

API_KEY = "your_api_key"
PROJECT_ID = "${currentProjectId}"
ENV = "${currentEnv}"
URL = f"${normalizedBaseUrl}/webhooks/trigger/{PROJECT_ID}/envs/{ENV}"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "messages": [
        {"role": "user", "content": "What is the capital of France?"}
    ]
}

response = requests.post(URL, json=payload, headers=headers)

if response.status_code == 202:
    print("Accepted. Workflow is running in the background.")
else:
    print("Error:", response.status_code, response.text)`,
    },
    {
      title: 'JavaScript',
      value: 'javascript',
      languageClass: 'language-javascript',
      icon: 'logos:javascript',
      code: `const apiKey = "your_api_key";
const projectId = "${currentProjectId}";
const env = "${currentEnv}";
const url = \`${normalizedBaseUrl}/webhooks/trigger/\${projectId}/envs/\${env}\`;

const headers = {
    "X-API-Key": apiKey,
    "Content-Type": "application/json"
};

const payload = {
    messages: [
        { role: "user", content: "What is the capital of France?" }
    ]
};

fetch(url, {
    method: "POST",
    headers: headers,
    body: JSON.stringify(payload)
})
.then(response => {
    if (response.status === 202) {
        console.log("Accepted. Workflow is running in the background.");
    }
})
.catch(error => console.error("Error:", error));`,
    },
    {
      title: 'cURL',
      value: 'curl',
      languageClass: 'language-bash',
      icon: 'vscode-icons:file-type-shell',
      code: `curl -X POST "${normalizedBaseUrl}/webhooks/trigger/${currentProjectId}/envs/${currentEnv}" \\
     -H "X-API-Key: your_api_key" \\
     -H "Content-Type: application/json" \\
     -d '{
       "messages": [
         {"role": "user", "content": "What is the capital of France?"}
       ]
     }'`,
    },
  ]
})

const activeLanguages = computed(() => (endpointMode.value === 'api' ? apiLanguages.value : webhookLanguages.value))

const copyUrlToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(activeUrl.value)
  } catch (err) {
    logger.error('Failed to copy URL', { error: err })
  }
}

// API Keys Management Functions
const fetchApiKeys = async () => {
  if (!computedProjectId.value) return

  loading.value = true
  error.value = null

  try {
    const response = await scopeoApi.apiKeys.getAll(computedProjectId.value)

    apiKeys.value = (response as ApiKeysResponse).api_keys
  } catch (err) {
    logger.error('Failed to fetch API keys', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to fetch API keys'
  } finally {
    loading.value = false
  }
}

const closeAndResetNewKeyDialog = () => {
  newKeyDialog.value = false
  generatedKey.value = ''
  newKeyName.value = ''
}

const generateNewKey = async () => {
  if (!computedProjectId.value) return

  try {
    const request: CreateApiKeyRequest = {
      key_name: newKeyName.value,
      project_id: computedProjectId.value,
    }

    const response = await scopeoApi.apiKeys.create(computedProjectId.value, request)
    const data = response as CreateApiKeyResponse

    generatedKey.value = data.private_key
    await fetchApiKeys() // Refresh the list
    newKeyDialog.value = true // Ensure dialog stays open to show the key
  } catch (err) {
    logger.error('Failed to generate API key', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to generate API key'
  }
}

const requestRevokeKey = (key: ApiKey) => {
  keyToRevoke.value = key
  showRevokeConfirmation.value = true
}

const confirmRevokeKey = async () => {
  if (!keyToRevoke.value || !computedProjectId.value) return

  try {
    const response = await scopeoApi.apiKeys.revoke(computedProjectId.value, { key_id: keyToRevoke.value.key_id })
    const data = response as RevokeKeyResponse

    if (data.message) {
      notify.success('API key revoked successfully')
    }

    await fetchApiKeys() // Refresh the list
  } catch (err) {
    logger.error('Failed to revoke API key', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to revoke API key'
  } finally {
    keyToRevoke.value = null
  }
}

const cancelRevoke = () => {
  keyToRevoke.value = null
}

const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(generatedKey.value)
  } catch (err) {
    logger.error('Failed to copy to clipboard', { error: err })
  }
}

// Fetch API keys when component mounts and when project ID changes
onMounted(() => {
  if (computedProjectId.value) {
    fetchApiKeys()
  }
})

// Watch for project ID changes (from agent, projectId prop, etc.)
watch(
  () => computedProjectId.value,
  newId => {
    if (newId) {
      fetchApiKeys()
    }
  }
)
</script>

<template>
  <div class="shared-api">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-3">
      <div>
        <h2 class="text-h5 mb-2">API Integration</h2>
        <p class="text-body-1 text-medium-emphasis">Use this {{ props.type }} via REST API in your applications.</p>
      </div>
    </div>

    <!-- API Keys Section -->
    <VCard class="mb-6">
      <VCardText>
        <div class="d-flex justify-space-between align-center mb-4">
          <h5 class="text-h5">Manage API Keys</h5>
          <VTooltip text="You need admin or developer permissions to generate API keys">
            <template #activator="{ props: tooltipProps }">
              <VBtn
                color="primary"
                prepend-icon="tabler-plus"
                :disabled="!ability.can('create', 'Project')"
                v-bind="tooltipProps"
                @click="ability.can('create', 'Project') ? (newKeyDialog = true) : null"
              >
                Generate New Key
              </VBtn>
            </template>
          </VTooltip>
        </div>

        <!-- API Keys Table -->
        <VProgressCircular v-if="loading" indeterminate color="primary" />
        <VAlert v-else-if="error" type="error" variant="tonal" class="mb-4">
          {{ error }}
        </VAlert>
        <VTable v-else class="api-keys-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in apiKeys" :key="key.key_id">
              <td>{{ key.key_name }}</td>
              <td>
                <VBtn
                  v-if="ability.can('delete', 'Project')"
                  size="x-small"
                  color="error"
                  variant="tonal"
                  @click="requestRevokeKey(key)"
                >
                  Revoke
                </VBtn>
              </td>
            </tr>
          </tbody>
        </VTable>
      </VCardText>
    </VCard>

    <!-- Info block -->
    <VAlert class="mb-4" type="info" variant="tonal" :icon="false">
      <div class="text-h6 font-weight-bold mb-3">Classic API vs. Webhook — What's the difference?</div>
      <VRow>
        <VCol cols="12" md="6">
          <div class="d-flex align-center mb-1">
            <VIcon icon="tabler-api" size="18" class="me-1" />
            <span class="text-subtitle-2 font-weight-bold me-2">Classic POST <code>/run</code></span>
            <VChip size="x-small" color="success">Synchronous</VChip>
          </div>
          <ul class="text-body-2 ps-4 mb-0">
            <li>Connection stays open until the workflow completes</li>
            <li>Response contains the full result immediately</li>
            <li>Best for short, fast workflows (&lt; 30s)</li>
          </ul>
        </VCol>
        <VCol cols="12" md="6">
          <div class="d-flex align-center mb-1">
            <VIcon icon="tabler-webhook" size="18" class="me-1" />
            <span class="text-subtitle-2 font-weight-bold me-2">Webhook <code>/webhooks/trigger</code></span>
            <VChip size="x-small" color="warning">Asynchronous</VChip>
          </div>
          <ul class="text-body-2 ps-4 mb-0">
            <li>Returns <code>202 Accepted</code> immediately (no body)</li>
            <li>Workflow runs in the background</li>
            <li>Best for long-running workflows or when you can't hold a connection open</li>
          </ul>
        </VCol>
      </VRow>
    </VAlert>

    <!-- API / Webhook toggle -->
    <div class="d-flex align-center mb-6">
      <VBtnToggle v-model="endpointMode" mandatory color="primary" rounded="lg" class="endpoint-toggle">
        <VBtn value="api" prepend-icon="tabler-api"> Classic API </VBtn>
        <VBtn value="webhook" prepend-icon="tabler-webhook"> Webhook </VBtn>
      </VBtnToggle>
    </div>

    <!-- Documentation rows -->
    <VRow>
      <!-- Documentation Card -->
      <VCol cols="12" md="6">
        <VCard>
          <VCardTitle class="d-flex justify-space-between align-center pt-6 px-6">
            <span class="text-h6">{{ endpointMode === 'api' ? 'API' : 'Webhook' }} Documentation</span>
            <VCheckbox v-model="isDevEnvironment" label="dev" color="primary" density="compact" hide-details />
          </VCardTitle>
          <VCardText>
            <div class="documentation-content">
              <h4 class="text-subtitle-1 font-weight-bold mb-2">Endpoint</h4>
              <p class="d-flex align-center mb-4">
                <strong class="me-2">URL:</strong>
                <code>{{ activeUrl }}</code>
                <VBtn
                  icon
                  variant="text"
                  size="x-small"
                  color="grey-lighten-1"
                  class="ms-2"
                  @click="copyUrlToClipboard"
                >
                  <VIcon size="18" icon="tabler-copy" />
                </VBtn>
              </p>
              <p class="mb-4"><strong>Method:</strong> <code>POST</code></p>

              <h4 class="text-subtitle-1 font-weight-bold mb-2">Headers</h4>
              <div class="mb-4">
                Authentication is required via an API key passed in the request header:
                <ul>
                  <li><code>X-API-Key</code>: Your secret API key. Generate and manage keys in the section above.</li>
                </ul>
              </div>

              <h4 class="text-subtitle-1 font-weight-bold mb-2">Request Body</h4>
              <p class="mb-2">
                Send a JSON payload containing a conversation. Optionally include <code>set_ids</code> to inject
                variable sets at runtime.
              </p>
              <VCard variant="flat" color="surface" class="mb-3 pa-4">
                <pre class="ma-0"><code>{
  "messages": [
    {"role": "user", "content": "Hello, how are you?"},
    {"role": "assistant", "content": "I'm doing well, thank you! How can I help you today?"},
    {"role": "user", "content": "What is the capital of France?"}
  ],
  "set_ids": ["defaults", "demo-custom"]
}</code></pre>
              </VCard>
              <p class="text-body-2 text-medium-emphasis mb-4">
                <strong>set_ids</strong> — Variable sets are named groups of values for your defined variables — for
                example, a "user_id" set that provides specific values associated with a particular user. They allow you
                to reuse the same variables with different value combinations. These values are injected at workflow
                runtime.
              </p>

              <!-- Classic API only -->
              <template v-if="endpointMode === 'api'">
                <h4 class="text-subtitle-1 font-weight-bold mb-2">Response Format</h4>
                <div class="mb-4">
                  <p class="mb-2">
                    The <code>response_format</code> is an optional parameter to control how generated files are
                    returned. Possible values:
                  </p>
                  <ul>
                    <li>
                      <strong>None</strong> (default): If you don't provide the <code>params</code> parameter, no files
                      will be returned in the response.
                    </li>
                    <li>
                      <strong>base64</strong>: Returns files as base64-encoded strings in the <code>files</code> array.
                    </li>
                    <li>
                      <strong>url</strong>: Returns presigned S3 URLs in the <code>files</code> array.
                      <strong>The presigned URL expires after 1 hour.</strong> Generated files are stored in an S3
                      bucket and deleted after 1 day.
                    </li>
                  </ul>
                </div>

                <h4 class="text-subtitle-1 font-weight-bold mb-2">Response</h4>
                <ul class="mb-4">
                  <li><strong>200 OK:</strong> Successfully processed the request.</li>
                  <li><strong>422 Unprocessable Entity:</strong> Validation error in the request body.</li>
                </ul>

                <h5 class="text-subtitle-1 font-weight-bold mb-2">Response Examples</h5>
                <div class="mb-3 d-flex gap-2 flex-wrap">
                  <VBtn
                    :variant="selectedResponseExample === 'base64' ? 'flat' : 'outlined'"
                    :color="selectedResponseExample === 'base64' ? 'primary' : 'default'"
                    size="small"
                    @click="selectedResponseExample = 'base64'"
                  >
                    base64
                  </VBtn>
                  <VBtn
                    :variant="selectedResponseExample === 'url' ? 'flat' : 'outlined'"
                    :color="selectedResponseExample === 'url' ? 'primary' : 'default'"
                    size="small"
                    @click="selectedResponseExample = 'url'"
                  >
                    url
                  </VBtn>
                  <VBtn
                    :variant="selectedResponseExample === 'no-file' ? 'flat' : 'outlined'"
                    :color="selectedResponseExample === 'no-file' ? 'primary' : 'default'"
                    size="small"
                    @click="selectedResponseExample = 'no-file'"
                  >
                    No file / None
                  </VBtn>
                </div>
                <VCard variant="flat" color="surface" class="mb-4 pa-4">
                  <pre class="ma-0"><code>{{ responseExamples.code }}</code></pre>
                </VCard>
              </template>

              <!-- Webhook only -->
              <template v-else>
                <h4 class="text-subtitle-1 font-weight-bold mb-2">Response</h4>
                <p class="mb-4">
                  The endpoint responds immediately with <code>202 Accepted</code> and no body — the workflow is now
                  running in the background.
                </p>

                <h4 class="text-subtitle-1 font-weight-bold mb-2">Response Codes</h4>
                <ul class="mb-4">
                  <li>
                    <strong>202 Accepted:</strong> Workflow triggered, running in the background. No response body.
                  </li>
                  <li><strong>422 Unprocessable Entity:</strong> Validation error in the request body.</li>
                  <li><strong>401 Unauthorized:</strong> Invalid or missing API key.</li>
                </ul>
              </template>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Code Examples Card -->
      <VCol cols="12" md="6">
        <VCard>
          <VCardTitle class="text-h6 pt-6 px-6">Code Examples</VCardTitle>
          <VCardText>
            <VTabs v-model="selectedLanguage" color="primary" class="mb-6">
              <VTab v-for="lang in activeLanguages" :key="lang.value" :value="lang.value">
                <VIcon :icon="lang.icon" size="20" class="me-2" />
                {{ lang.title }}
              </VTab>
            </VTabs>

            <VWindow v-model="selectedLanguage">
              <VWindowItem v-for="lang in activeLanguages" :key="lang.value" :value="lang.value">
                <VCard variant="flat" color="transparent" class="code-block">
                  <pre><code
                    :key="lang.code"
                    v-highlight:[lang.value]="lang.code"
                    :class="lang.languageClass"
                  ></code></pre>
                </VCard>
              </VWindowItem>
            </VWindow>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- New API Key Dialog -->
    <VDialog v-model="newKeyDialog" max-width="var(--dnr-dialog-md)" persistent>
      <VCard>
        <VCardTitle class="d-flex justify-space-between align-center">
          <span>Generate New API Key</span>
          <VBtn icon variant="text" @click="closeAndResetNewKeyDialog">
            <VIcon>tabler-x</VIcon>
          </VBtn>
        </VCardTitle>
        <VCardText>
          <VTextField
            v-if="!generatedKey"
            v-model="newKeyName"
            label="Key Name"
            placeholder="e.g., Production API Key"
            class="mb-4"
          />

          <VAlert v-if="generatedKey" color="warning" class="mb-4">
            <p class="mb-2">Make sure to copy your API key now. You won't be able to see it again!</p>
            <VTextField :model-value="generatedKey" readonly variant="outlined" density="compact">
              <template #append>
                <VBtn size="small" variant="text" color="primary" @click="copyToClipboard"> Copy </VBtn>
              </template>
            </VTextField>
          </VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn v-if="generatedKey" color="primary" @click="closeAndResetNewKeyDialog"> Done </VBtn>
          <VBtn v-else color="primary" :disabled="!newKeyName" @click="generateNewKey"> Generate </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Revoke Confirmation Dialog -->
    <GenericConfirmDialog
      v-if="keyToRevoke"
      v-model:is-dialog-visible="showRevokeConfirmation"
      title="Confirm Revoke"
      :message="`Are you sure you want to revoke the API key <strong>${keyToRevoke.key_name}</strong>? This action cannot be undone.`"
      confirm-text="Revoke"
      confirm-color="error"
      @confirm="confirmRevokeKey"
      @cancel="cancelRevoke"
    />
  </div>
</template>

<style lang="scss" scoped>
.shared-api {
  .documentation-content {
    code {
      border-radius: 4px;
      background: rgba(var(--v-theme-on-surface), 0.05);
      font-family: monospace;
      font-size: 0.875em;
      padding-block: 0.2rem;
      padding-inline: 0.4rem;
    }

    pre {
      overflow-x: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  }

  .code-block {
    overflow: hidden;
    border: none;
    border-radius: 4px;
    background-color: transparent;

    pre {
      padding: 1em;
      margin: 0;
      overflow-x: auto;
      white-space: pre-wrap;
      word-wrap: break-word;

      code {
        padding: 0 !important;
        background: none !important;
        color: rgb(var(--v-theme-on-surface));
        font-family: 'Fira Code', monospace;
        font-size: 0.9em;
      }
    }
  }

  .endpoint-toggle {
    /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
    :deep(.v-btn) {
      min-width: 160px;
      padding-inline: 1rem;
      block-size: 22px;
    }
  }

  .api-keys-table {
    /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
    :deep(th) {
      font-weight: 600;
      text-transform: uppercase;
      white-space: nowrap;
    }

    /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
    :deep(td) {
      block-size: 3.5rem;
      vertical-align: middle;
    }
  }
}
</style>
