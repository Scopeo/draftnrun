// Test utilities for iframe integration
export interface TestWorkflowState {
  prompt: string
  components: any[]
  companyName: string
  theme: string
}

export interface TestMessage {
  type: string
  data: any
}

// Mock workflow state for testing
export const mockWorkflowState: TestWorkflowState = {
  prompt: 'Customer support bot for e-commerce store',
  components: [
    {
      id: '1',
      type: 'ai-response',
      title: 'AI Agent',
      content: 'Customer support bot for e-commerce store',
      icon: '🤖',
      isPremium: false,
    },
    {
      id: '2',
      type: 'knowledge',
      title: 'Document Knowledge',
      content: 'Upload files to enhance AI responses with your data',
      icon: '📄',
      isPremium: true,
    },
  ],
  companyName: 'Test Company',
  theme: '#93c5fd',
}

// Test message types
export const TEST_MESSAGES = {
  SHOW_SIGNUP_MODAL: 'SHOW_SIGNUP_MODAL',
  SIGNUP_REQUEST: 'SIGNUP_REQUEST',
  LOGIN_REQUEST: 'LOGIN_REQUEST',
  RESTORE_WORKFLOW_STATE: 'RESTORE_WORKFLOW_STATE',
  CLOSE_MODAL: 'CLOSE_MODAL',
} as const

// Helper to create test messages
export function createTestMessage(type: string, data: any): TestMessage {
  return { type, data }
}

// Helper to simulate iframe communication
export function simulateIframeMessage(type: string, data: any) {
  const message = createTestMessage(type, data)

  // Dispatch to window (for testing in browser console)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new MessageEvent('message', {
        data: message,
        origin: 'http://localhost:3000', // Mock origin
      })
    )
  }

  return message
}

// Helper to test workflow state restoration
export function testWorkflowRestoration() {
  return simulateIframeMessage(TEST_MESSAGES.RESTORE_WORKFLOW_STATE, {
    workflowState: mockWorkflowState,
  })
}

// Helper to test signup modal
export function testSignupModal() {
  return simulateIframeMessage(TEST_MESSAGES.SHOW_SIGNUP_MODAL, {
    reason: 'Unlock Slack Integration to enhance your chatbot with deploy bot to slack channels!',
    suggestion: {
      id: 'slack',
      title: 'Slack Integration',
      description: 'Deploy bot to Slack channels',
      icon: 'tabler-brand-slack',
      color: '#4A154B',
    },
    workflowState: mockWorkflowState,
  })
}

// Helper to test signup request
export function testSignupRequest() {
  return simulateIframeMessage(TEST_MESSAGES.SIGNUP_REQUEST, {
    reason: 'Unlock premium features to enhance your chatbot!',
    workflowState: mockWorkflowState,
  })
}

// Helper to test modal close
export function testModalClose() {
  return simulateIframeMessage(TEST_MESSAGES.CLOSE_MODAL, {})
}

// Console testing helpers (for browser dev tools)
export const testHelpers = {
  // Test all message types
  testAll: () => {
    console.log('🧪 Testing all iframe communication...')
    testWorkflowRestoration()
    setTimeout(() => testSignupModal(), 1000)
    setTimeout(() => testSignupRequest(), 2000)
    setTimeout(() => testModalClose(), 3000)
  },

  // Test workflow restoration
  testRestore: testWorkflowRestoration,

  // Test signup modal
  testModal: testSignupModal,

  // Test signup request
  testSignup: testSignupRequest,

  // Test modal close
  testClose: testModalClose,

  // Show mock data
  showMockData: () => {
    console.log('📋 Mock Workflow State:', mockWorkflowState)
    console.log('📨 Test Messages:', TEST_MESSAGES)
  },
}

// Make test helpers available globally in development
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  ;(window as any).testHelpers = testHelpers
  console.log('🧪 Test helpers available at window.testHelpers')
  console.log('📖 Usage: testHelpers.testAll() or testHelpers.testModal()')
}
