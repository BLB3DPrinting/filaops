import { describe, it, expect } from 'vitest'
import {
  BASE_COLORS,
  PRODUCTION_ORDER_BADGE_CONFIGS,
  PRODUCTION_ORDER_COLORS,
  SALES_ORDER_COLORS,
  getStatusColor,
} from '../statusColors'

describe('statusColors', () => {
  describe('BASE_COLORS', () => {
    it('has all expected color keys', () => {
      const expectedKeys = ['gray', 'yellow', 'blue', 'purple', 'green', 'red', 'orange', 'cyan']
      for (const key of expectedKeys) {
        expect(BASE_COLORS[key]).toBeDefined()
      }
    })

    it('each color contains bg and text classes', () => {
      for (const [key, value] of Object.entries(BASE_COLORS)) {
        expect(value).toContain('bg-')
        expect(value).toContain('text-')
      }
    })
  })

  describe('PRODUCTION_ORDER_BADGE_CONFIGS', () => {
    it('has config for all production statuses', () => {
      const statuses = ['draft', 'released', 'in_progress', 'complete', 'short', 'cancelled']
      for (const status of statuses) {
        const config = PRODUCTION_ORDER_BADGE_CONFIGS[status]
        expect(config).toBeDefined()
        expect(config.bg).toBeDefined()
        expect(config.text).toBeDefined()
        expect(config.label).toBeDefined()
      }
    })

    it('has correct labels', () => {
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.draft.label).toBe('Draft')
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.in_progress.label).toBe('In Progress')
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.complete.label).toBe('Complete')
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.cancelled.label).toBe('Cancelled')
    })

    it('uses appropriate color classes (Workbench tokens, #846)', () => {
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.draft.bg).toContain('paper-sunk')
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.complete.text).toContain('green')
      expect(PRODUCTION_ORDER_BADGE_CONFIGS.cancelled.text).toContain('red')
    })
  })

  describe('SALES_ORDER_COLORS', () => {
    it('maps all expected sales statuses', () => {
      const statuses = ['pending', 'confirmed', 'in_production', 'ready_to_ship', 'shipped', 'completed', 'cancelled']
      for (const status of statuses) {
        expect(SALES_ORDER_COLORS[status]).toBeDefined()
      }
    })
  })

  describe('getStatusColor', () => {
    it('returns the correct color for a known status', () => {
      const result = getStatusColor(PRODUCTION_ORDER_COLORS, 'draft')
      expect(result).toBe(PRODUCTION_ORDER_COLORS.draft)
      expect(result).toContain('paper-sunk')
    })

    it('returns fallback for unknown status', () => {
      const result = getStatusColor(PRODUCTION_ORDER_COLORS, 'nonexistent', BASE_COLORS.red)
      expect(result).toBe(BASE_COLORS.red)
    })

    it('returns gray as default when no fallback provided', () => {
      const result = getStatusColor(PRODUCTION_ORDER_COLORS, 'nonexistent')
      expect(result).toBe(BASE_COLORS.gray)
    })
  })
})
