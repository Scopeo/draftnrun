<script setup lang="ts">
import { logger } from '@/utils/logger'
import { useApiEnvironment } from '@/composables/useApiEnvironment'
import vHighlight from '@/directives/vHighlight'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github-dark.css'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('bash', bash)

const { environment } = useApiEnvironment()

const apiBaseUrl = import.meta.env.VITE_SCOPEO_API_URL

const route = useRoute()
const projectId = route.params.id as string
const orgId = route.params.orgId as string

const apiUrl = computed(() => `${apiBaseUrl}/projects/${projectId}/${environment.value}/run`)

const isDevEnvironment = computed({
  get: () => environment.value === 'draft',
  set: value => {
    environment.value = value ? 'draft' : 'production'
  },
})

const selectedLanguage = ref('python')

const languages = computed(() => {
  const currentProjId = projectId
  const currentEnv = environment.value

  return [
    {
      title: 'Python',
      value: 'python',
      languageClass: 'language-python',
      icon: 'logos:python',
      code: `import requests\n\nAPI_KEY = "your_api_key"\nPROJECT_ID = "${currentProjId}"\nURL = f"${apiBaseUrl}/projects/${currentProjId}/${currentEnv}/run"\n\nheaders = {\n    "X-API-Key": API_KEY,\n    "Content-Type": "application/json"\n}\n\npayload = {\n    "messages": [\n        {"role": "user", "content": "Hello, how are you?"},\n        {"role": "assistant", "content": "I'm doing well, thank you! How can I help you today?"},\n        {"role": "user", "content": "What is the capital of France?"},\n        {"role": "assistant", "content": "The capital of France is Paris."},\n        {"role": "user", "content": "Where I can go to see the Eiffel Tower?"},\n        {"role": "assistant", "content": "You can go to the Eiffel Tower in Paris, France."},\n        {"role": "user", "content": "Thank you"}\n    ]\n}\n\nresponse = requests.post(URL, json=payload, headers=headers)\n\nif response.status_code == 200:\n    print("Success:", response.json())\nelse:\n    print("Error:", response.status_code, response.text)`,
    },
    {
      title: 'JavaScript',
      value: 'javascript',
      languageClass: 'language-javascript',
      icon: 'logos:javascript',
      code: `const apiKey = "your_api_key";\nconst projectId = "${currentProjId}";\nconst env = "${currentEnv}"; \nconst url = \`${apiBaseUrl}/projects/\${projectId}/\${env}/run\`;\n\nheaders = {\n    "X-API-Key": apiKey,\n    "Content-Type": "application/json"\n};\n\nconst payload = {\n    messages: [\n        { role: "user", content: "Hello, how are you?" },\n        { role: "assistant", content: "I'm doing well, thank you! How can I help you today?" },\n        { role: "user", content: "What is the capital of France?" },\n        { role: "assistant", content: "The capital of France is Paris." },\n        { role: "user", content: "Where I can go to see the Eiffel Tower?" },\n        { role: "assistant", content: "You can go to the Eiffel Tower in Paris, France." },\n        { role: "user", content: "Thank you" }\n    ]\n};\n\nfetch(url, {\n    method: "POST",\n    headers: headers,\n    body: JSON.stringify(payload)\n})\n.then(response => response.json())\n.then(data => logger.info("Success:", data))\n.catch(error => logger.error("Error"', { error: error }));`,
    },
    {
      title: 'cURL',
      value: 'curl',
      languageClass: 'language-bash',
      icon: 'vscode-icons:file-type-shell',
      code: `curl -X POST "${apiBaseUrl}/projects/${currentProjId}/${currentEnv}/run" \\\n     -H "X-API-Key: your_api_key" \\\n     -H "Content-Type: application/json" \\\n     -d '{\n       "messages": [\n         {"role": "user", "content": "Hello, how are you?"},\n         {"role": "assistant", "content": "I'\''m doing well, thank you! How can I help you today?"},\n         {"role": "user", "content": "What is the capital of France?"},\n         {"role": "assistant", "content": "The capital of France is Paris."},\n         {"role": "user", "content": "Where I can go to see the Eiffel Tower?"},\n         {"role": "assistant", "content": "You can go to the Eiffel Tower in Paris, France."},\n         {"role": "user", "content": "Thank you"}\n       ]\n     }'`,
    },
  ]
})

const copyUrlToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(apiUrl.value)
  } catch (err) {
    logger.error('Failed to copy API URL', { error: err })
  }
}
</script>

<template>
  <VRow>
    <!-- Documentation Card -->
    <VCol cols="12" md="6">
      <VCard>
        <VCardTitle class="d-flex justify-space-between align-center pt-6 px-6">
          <span class="text-h6">API Documentation</span>
          <VCheckbox v-model="isDevEnvironment" label="dev" color="primary" density="compact" hide-details />
        </VCardTitle>
        <VCardText>
          <div class="documentation-content">
            <h4 class="text-subtitle-1 font-weight-bold mb-2">Endpoint</h4>
            <p class="d-flex align-center mb-4">
              <strong class="me-2">URL:</strong>
              <code>{{ apiUrl }}</code>
              <VBtn icon variant="text" size="x-small" color="grey-lighten-1" class="ms-2" @click="copyUrlToClipboard">
                <VIcon size="18" icon="tabler-copy" />
              </VBtn>
            </p>
            <p class="mb-4"><strong>Method:</strong> <code>POST</code></p>

            <h4 class="text-subtitle-1 font-weight-bold mb-2">Headers</h4>
            <div class="mb-4">
              Authentication is required via an API key passed in the request header:
              <ul>
                <li>
                  <code>X-API-Key</code>: Your secret API key. You can generate and manage keys in the
                  <RouterLink :to="{ name: 'org-org-id-projects-id', params: { orgId, id: projectId } }">
                    API Keys
                  </RouterLink>
                  section.
                </li>
              </ul>
            </div>

            <h4 class="text-subtitle-1 font-weight-bold mb-2">Request Body</h4>
            <p class="mb-2">Send a JSON payload containing the whole conversation:</p>
            <VCard variant="flat" color="surface" class="mb-4 pa-4">
              <pre class="ma-0"><code>{
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"
    },
    {
      "role": "assistant",
      "content": "I'm doing well, thank you! How can I help you today?"
    },
    {
      "role": "user",
      "content": "What is the capital of France?"
    },
    {
      "role": "assistant",
      "content": "The capital of France is Paris."
    },
    {
      "role": "user",
      "content": "Where I can go to see the Eiffel Tower?"
    },
    {
      "role": "assistant",
      "content": "You can go to the Eiffel Tower in Paris, France."
    },
    {
      "role": "user",
      "content": "Thank you"
    }
  ]
}</code></pre>
            </VCard>

            <h4 class="text-subtitle-1 font-weight-bold mb-2">Response</h4>
            <ul class="mb-4">
              <li><strong>200 OK:</strong> Successfully processed the request.</li>
              <li><strong>422 Unprocessable Entity:</strong> Validation error in the request body.</li>
            </ul>
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
            <VTab v-for="lang in languages" :key="lang.value" :value="lang.value">
              <VIcon :icon="lang.icon" size="20" class="me-2" />
              {{ lang.title }}
            </VTab>
          </VTabs>

          <VWindow v-model="selectedLanguage">
            <VWindowItem v-for="lang in languages" :key="lang.value" :value="lang.value">
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
</template>

<style lang="scss" scoped>
.documentation-content {
  code {
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.05);
    font-family: monospace;
    font-size: 0.875em;
    padding-block: 0.2rem;
    padding-inline: 0.4rem;
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
</style>
