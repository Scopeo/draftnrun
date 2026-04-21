import { type ComputedRef, type Ref, ref } from 'vue'
import { useVueFlow } from '@vue-flow/core'
import { VFileInput } from 'vuetify/components/VFileInput'
import { VSelect } from 'vuetify/components/VSelect'
import { VSlider } from 'vuetify/components/VSlider'
import { VSwitch } from 'vuetify/components/VSwitch'
import { VTextarea } from 'vuetify/components/VTextarea'
import { VTextField } from 'vuetify/components/VTextField'
import FieldExpressionInput from '@/components/studio/inputs/FieldExpressionInput.vue'
import OAuthConnectionInput from '@/components/studio/inputs/OAuthConnectionInput.vue'
import CategoriesBuilder from '@/components/studio/components/CategoriesBuilder.vue'
import ConditionBuilder from '@/components/studio/components/ConditionBuilder.vue'
import JsonTextarea from '@/components/studio/components/JsonTextarea.vue'
import MultiSelectChipGroup from '@/components/studio/components/MultiSelectChipGroup.vue'
import PayloadBuilder from '@/components/studio/components/PayloadBuilder.vue'
import RouterConfigBuilder from '@/components/studio/components/RouterConfigBuilder.vue'
import {
  type ComponentConfig,
  EXCLUDED_FROM_INJECTION,
  type SidebarParameter,
  type Source,
  normalizeUiComponent,
  validateFileSize,
} from '@/components/studio/components/edit-sidebar/types'
import type { FormDataShape } from '@/components/studio/components/edit-sidebar/form-initializer'
import { useLLMCredits } from '@/composables/useLLMCredits'

export function useEditSidebarComponentConfig(
  componentData: ComputedRef<any>,
  componentDefinition: ComputedRef<any>,
  componentDefinitions: ComputedRef<any[]>,
  formData: Ref<FormDataShape>,
  sources: Ref<Source[]>,
  isReadOnlyMode: ComputedRef<boolean>,
  isWorker: ComputedRef<boolean>,
  projects: ComputedRef<any[]>
) {
  const { nodes, edges } = useVueFlow()
  const { getLLMModelItems } = useLLMCredits()

  const showProjectSelectionDialog = ref(false)

  const handleProjectSelection = (projectId: string) => {
    if (componentData.value?.component_id === '4c8f9e2d-1a3b-4567-8901-234567890abc')
      formData.value.parameters.project_id = projectId
  }

  const getProjectName = (projectId: string) => {
    if (!projectId) return null
    const project = projects.value?.find(p => p.project_id === projectId)
    return project?.project_name || null
  }

  const getGraphNodesData = () => nodes.value.map(n => ({ id: n.id, ...n.data }))

  function getComponentConfig(param: SidebarParameter): ComponentConfig {
    if (componentData.value?.component_id === '4c8f9e2d-1a3b-4567-8901-234567890abc' && param.name === 'project_id') {
      const projectId = formData.value.parameters[param.name]
      const projectName = projectId ? getProjectName(projectId) : null
      return {
        component: VTextField,
        props: {
          label: param.ui_component_properties?.label || 'Project Reference',
          placeholder: projectName ? undefined : 'Click to select project...',
          readonly: true,
          appendInnerIcon: 'tabler-folder-open',
          onClick: () => (showProjectSelectionDialog.value = true),
          'onClick:appendInner': () => (showProjectSelectionDialog.value = true),
          modelValue: projectName || '',
          hint: projectName ? 'Reference' : undefined,
          persistentHint: !!projectName,
          class: projectName ? 'project-reference-field' : undefined,
        },
      }
    }

    const isFileType = param.ui_component === 'FileUpload'
    if (isFileType) {
      const fileValue = formData.value.parameters[param.name] as unknown
      const isBase64String = typeof fileValue === 'string' && fileValue.length > 0 && !fileValue.startsWith('data:')
      if (isReadOnlyMode.value) {
        let fileName = ''
        if (fileValue instanceof File) fileName = fileValue.name
        else if (fileValue && typeof fileValue === 'object' && 'name' in fileValue)
          fileName = String((fileValue as { name?: unknown }).name || '')
        else if (isBase64String || (typeof fileValue === 'string' && fileValue.length > 0)) fileName = 'File uploaded'
        return {
          component: VTextField,
          props: {
            label: param.ui_component_properties?.label,
            readonly: true,
            variant: 'outlined',
            modelValue: fileName,
          },
        }
      }
      return {
        component: VFileInput,
        props: {
          label: param.ui_component_properties?.label,
          accept: param.ui_component_properties?.accept || '.doc,.docx',
          multiple: param.ui_component_properties?.multiple || false,
          required: !param.nullable,
          showSize: true,
          variant: 'outlined',
          rules: [validateFileSize],
        },
      }
    }

    const uiComponent = normalizeUiComponent(param.ui_component)
    const TEXT_BASED_COMPONENTS = ['TEXTFIELD', 'TEXTAREA', '']
    if (EXCLUDED_FROM_INJECTION.includes(param.name) && TEXT_BASED_COMPONENTS.includes(uiComponent)) {
      return {
        component: VTextarea,
        props: {
          label: param.ui_component_properties?.label || param.name,
          placeholder: param.ui_component_properties?.placeholder,
          rows: param.name === 'output_format' ? 10 : 3,
          readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
        },
      }
    }

    switch (uiComponent) {
      case 'JSON_TEXTAREA':
      case 'JSONTEXTAREA':
        return {
          component: JsonTextarea,
          props: {
            label: param.ui_component_properties?.label || param.name,
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            graphNodes: getGraphNodesData(),
            graphEdges: edges.value,
            currentNodeId: componentData.value?.id,
            componentDefinitions: componentDefinitions.value,
            enableAutocomplete: true,
            targetInstanceId: componentData.value?.id,
          },
        }
      case 'JSON_BUILDER':
        return {
          component: PayloadBuilder,
          props: {
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            color: isWorker.value ? 'secondary' : 'primary',
          },
        }
      case 'CATEGORIESBUILDER':
        return {
          component: CategoriesBuilder,
          props: {
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            color: isWorker.value ? 'secondary' : 'primary',
            label: param.ui_component_properties?.label || 'Categories',
            description:
              param.ui_component_properties?.description || 'Define the categories you want to classify content into.',
          },
        }
      case 'CHECKBOX':
        return {
          component: VSwitch,
          props: {
            trueValue: true,
            falseValue: false,
            label: param.ui_component_properties?.label,
            disabled: isReadOnlyMode.value,
            color: isWorker.value ? 'secondary' : 'primary',
          },
        }
      case 'SLIDER':
        return {
          component: VSlider,
          props: {
            min: param.ui_component_properties?.min || 0,
            max: param.ui_component_properties?.max || 100,
            step: param.ui_component_properties?.step || 1,
            label: param.ui_component_properties?.label,
            disabled: isReadOnlyMode.value,
          },
        }
      case 'TEXTAREA':
        return {
          component: FieldExpressionInput,
          props: {
            label: param.ui_component_properties?.label || param.name,
            alertMessage: param.ui_component_properties?.alert_message,
            placeholder: param.ui_component_properties?.placeholder,
            isTextarea: true,
            graphNodes: getGraphNodesData(),
            graphEdges: edges.value,
            currentNodeId: componentData.value?.id,
            componentDefinitions: componentDefinitions.value,
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            enableAutocomplete: true,
            targetInstanceId: componentData.value?.id,
          },
        }
      case 'CODE': {
        const textareaConfig: ComponentConfig = getComponentConfig({ ...param, ui_component: 'TEXTAREA' })
        return { ...textareaConfig, props: { ...textareaConfig.props, disableMarkdown: true } }
      }
      case 'CONDITIONBUILDER':
        return {
          component: ConditionBuilder,
          props: {
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            color: isWorker.value ? 'secondary' : 'primary',
            graphNodes: getGraphNodesData(),
            graphEdges: edges.value,
            currentNodeId: componentData.value?.id,
            componentDefinitions: componentDefinitions.value,
            targetInstanceId: componentData.value?.id,
          },
        }
      case 'OAUTH_CONNECTION':
      case 'OAUTHCONNECTION':
        return {
          component: OAuthConnectionInput,
          props: {
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            provider: param.ui_component_properties?.provider || 'unknown',
            icon: param.ui_component_properties?.icon,
            label: param.ui_component_properties?.label || param.name,
            description: param.ui_component_properties?.description,
          },
        }
      case 'ROUTEBUILDER':
        return {
          component: RouterConfigBuilder,
          props: {
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            color: 'info',
            graphNodes: getGraphNodesData(),
            graphEdges: edges.value,
            currentNodeId: componentData.value?.id,
            componentDefinitions: componentDefinitions.value,
            targetInstanceId: componentData.value?.id,
          },
        }
      case 'SELECT':
        if (isReadOnlyMode.value)
          return {
            component: VTextField,
            props: { label: param.ui_component_properties?.label, readonly: true, variant: 'outlined' },
          }
        if (param.type === 'data_source')
          return {
            component: VSelect,
            props: {
              items: sources.value.map(s => ({ title: s.name, value: s.id })),
              label: param.ui_component_properties?.label,
              itemTitle: 'title',
              itemValue: 'value',
              multiple: true,
              chips: true,
              closableChips: true,
              required: !param.nullable,
            },
          }
        if (param.type === 'llm_model') {
          const items = getLLMModelItems(param.ui_component_properties?.options || [])
          return {
            component: VSelect,
            props: {
              items,
              label: param.ui_component_properties?.label,
              itemTitle: 'title',
              itemSubtitle: 'subtitle',
              itemValue: 'value',
              required: !param.nullable,
            },
          }
        }
        return {
          component: VSelect,
          props: {
            items:
              param.ui_component_properties?.options?.map((o: { label: string; value: any }) => ({
                title: o.label,
                value: o.value,
              })) || [],
            label: param.ui_component_properties?.label,
            itemTitle: 'title',
            itemValue: 'value',
            required: !param.nullable,
          },
        }
      case 'MULTISELECT':
        if (isReadOnlyMode.value) {
          const selectedValues = Array.isArray(formData.value.parameters[param.name])
            ? (formData.value.parameters[param.name] as string[]).join(', ')
            : ''

          return {
            component: VTextField,
            props: {
              label: param.ui_component_properties?.label,
              modelValue: selectedValues,
              readonly: true,
              variant: 'outlined',
            },
          }
        }
        return {
          component: MultiSelectChipGroup,
          props: {
            label: param.ui_component_properties?.label,
            items: param.ui_component_properties?.options?.map((o: { label: string; value: any }) => o.value) || [],
            disabled: isReadOnlyMode.value,
          },
        }
      case 'EDITORS':
        return {
          component: VTextarea,
          props: {
            rows: 10,
            label: param.ui_component_properties?.label,
            resizable: true,
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
          },
        }
      default:
        if (param.type === 'integer')
          return {
            component: VTextField,
            props: {
              label: param.ui_component_properties?.label || param.name,
              placeholder: param.ui_component_properties?.placeholder,
              type: 'number',
              step: '1',
              min: param.ui_component_properties?.min,
              max: param.ui_component_properties?.max,
              variant: 'outlined',
              readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            },
          }
        if (param.type === 'number')
          return {
            component: VTextField,
            props: {
              label: param.ui_component_properties?.label || param.name,
              placeholder: param.ui_component_properties?.placeholder,
              type: 'number',
              step: param.ui_component_properties?.step || '0.1',
              min: param.ui_component_properties?.min,
              max: param.ui_component_properties?.max,
              variant: 'outlined',
              readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            },
          }
        return {
          component: FieldExpressionInput,
          props: {
            label: param.ui_component_properties?.label,
            alertMessage: param.ui_component_properties?.alert_message,
            placeholder: param.ui_component_properties?.placeholder,
            isTextarea: false,
            graphNodes: getGraphNodesData(),
            graphEdges: edges.value,
            currentNodeId: componentData.value?.id,
            componentDefinitions: componentDefinitions.value,
            readonly: isReadOnlyMode.value || !!param.ui_component_properties?.readonly,
            enableAutocomplete: true,
            targetInstanceId: componentData.value?.id,
          },
        }
    }
  }

  return { getComponentConfig, showProjectSelectionDialog, handleProjectSelection }
}
