export enum IfElseOperator {
  // Unary operators
  IS_EMPTY = 'is_empty',
  IS_NOT_EMPTY = 'is_not_empty',

  // Number operators
  NUMBER_GREATER_THAN = 'number_greater_than',
  NUMBER_LESS_THAN = 'number_less_than',
  NUMBER_EQUAL_TO = 'number_equal_to',
  NUMBER_GREATER_OR_EQUAL = 'number_greater_or_equal',
  NUMBER_LESS_OR_EQUAL = 'number_less_or_equal',

  // Boolean operators
  BOOLEAN_IS_TRUE = 'boolean_is_true',
  BOOLEAN_IS_FALSE = 'boolean_is_false',

  // Text operators
  TEXT_CONTAINS = 'text_contains',
  TEXT_DOES_NOT_CONTAIN = 'text_does_not_contain',
  TEXT_EQUALS = 'text_equals',
  TEXT_DOES_NOT_EQUAL = 'text_does_not_equal',
}

export interface OperatorDefinition {
  value: string
  label: string
  requires_value_b: boolean
  category?: 'unary' | 'number' | 'boolean' | 'text'
}

export interface Condition {
  value_a: string
  operator: string
  value_b?: string
  logical_operator?: 'AND' | 'OR'
}

export const AVAILABLE_OPERATORS: OperatorDefinition[] = [
  // Unary operators
  {
    value: IfElseOperator.IS_EMPTY,
    label: 'Is empty',
    requires_value_b: false,
    category: 'unary',
  },
  {
    value: IfElseOperator.IS_NOT_EMPTY,
    label: 'Is not empty',
    requires_value_b: false,
    category: 'unary',
  },

  // Number operators
  {
    value: IfElseOperator.NUMBER_GREATER_THAN,
    label: '[Number] Is greater than',
    requires_value_b: true,
    category: 'number',
  },
  {
    value: IfElseOperator.NUMBER_LESS_THAN,
    label: '[Number] Is less than',
    requires_value_b: true,
    category: 'number',
  },
  {
    value: IfElseOperator.NUMBER_EQUAL_TO,
    label: '[Number] Is equal to',
    requires_value_b: true,
    category: 'number',
  },
  {
    value: IfElseOperator.NUMBER_GREATER_OR_EQUAL,
    label: '[Number] Is greater than or equal to',
    requires_value_b: true,
    category: 'number',
  },
  {
    value: IfElseOperator.NUMBER_LESS_OR_EQUAL,
    label: '[Number] Is less than or equal to',
    requires_value_b: true,
    category: 'number',
  },

  // Boolean operators
  {
    value: IfElseOperator.BOOLEAN_IS_TRUE,
    label: '[Boolean] Is true',
    requires_value_b: false,
    category: 'boolean',
  },
  {
    value: IfElseOperator.BOOLEAN_IS_FALSE,
    label: '[Boolean] Is false',
    requires_value_b: false,
    category: 'boolean',
  },

  // Text operators
  {
    value: IfElseOperator.TEXT_CONTAINS,
    label: '[Text] Contains',
    requires_value_b: true,
    category: 'text',
  },
  {
    value: IfElseOperator.TEXT_DOES_NOT_CONTAIN,
    label: '[Text] Does not contain',
    requires_value_b: true,
    category: 'text',
  },
  {
    value: IfElseOperator.TEXT_EQUALS,
    label: '[Text] Equals',
    requires_value_b: true,
    category: 'text',
  },
  {
    value: IfElseOperator.TEXT_DOES_NOT_EQUAL,
    label: '[Text] Does not equal',
    requires_value_b: true,
    category: 'text',
  },
]
