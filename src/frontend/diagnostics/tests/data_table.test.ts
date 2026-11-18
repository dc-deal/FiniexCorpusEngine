import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DataTable from '@/components/base/DataTable.vue'

describe('the library\'s data table (179, step 3)', () => {
  it('holds a view\'s head and bodies in one scroll box, its grid from the columns given', () => {
    const table = mount(DataTable, {
      props: { columns: [{ width: '6rem' }, {}], minWidth: '48rem', fixed: true, tableClass: 'grouped-rows ruled' },
      slots: { head: '<tr><th>PDF page</th><th>Why</th></tr>', default: '<tbody><tr><td>p. 1</td><td>fine</td></tr></tbody>' },
    })
    expect(table.classes()).toContain('data-scroll')
    const element = table.find('table')
    expect(element.classes()).toEqual(expect.arrayContaining(['data-table', 'grouped-rows', 'ruled', 'fixed']))
    expect(element.attributes('style')).toContain('min-width: 48rem')
    expect(table.findAll('col').map(col => col.attributes('style') ?? '')).toEqual(['width: 6rem;', ''])
    expect(table.find('thead th').text()).toBe('PDF page')
    expect(table.find('tbody td').text()).toBe('p. 1')
  })

  it('draws no grid and no head where a view gives none', () => {
    const table = mount(DataTable, { slots: { default: '<tbody><tr><td>one</td></tr></tbody>' } })
    expect(table.find('colgroup').exists()).toBe(false)
    expect(table.find('thead').exists()).toBe(false)
  })
})
