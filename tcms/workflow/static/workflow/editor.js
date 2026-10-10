document.addEventListener('DOMContentLoaded', () => {
  const rows = document.getElementById('workflow-step-rows')
  const total = document.getElementById('id_steps-TOTAL_FORMS')
  const template = document.getElementById('workflow-step-template')
  const add = document.getElementById('workflow-add-step')
  if (!rows || !total || !template || !add) return
  const order = () => {
    let position = 0
    rows.querySelectorAll('[data-step-row]').forEach(row => {
      if (!row.hidden) row.querySelector('input[name$="-ORDER"]').value = position++
    })
  }
  add.addEventListener('click', () => {
    const index = Number(total.value)
    if (index >= 200) return
    const fragment = document.createElement('template')
    fragment.innerHTML = template.innerHTML.replaceAll('__prefix__', String(index))
    rows.appendChild(fragment.content.cloneNode(true))
    total.value = index + 1
    order()
  })
  rows.addEventListener('click', event => {
    const button = event.target.closest('button')
    const row = button && button.closest('[data-step-row]')
    if (!row) return
    if (button.hasAttribute('data-remove')) {
      row.querySelector('input[name$="-DELETE"]').checked = true
      row.hidden = true
    } else if (button.dataset.move) {
      const active = [...rows.querySelectorAll('[data-step-row]')].filter(item => !item.hidden)
      const index = active.indexOf(row)
      if (button.dataset.move === 'up' && index > 0) rows.insertBefore(row, active[index - 1])
      if (button.dataset.move === 'down' && index < active.length - 1) rows.insertBefore(active[index + 1], row)
    }
    order()
  })
  rows.querySelectorAll('[data-step-row]').forEach(row => {
    if (row.querySelector('input[name$="-DELETE"]').checked) row.hidden = true
  })
  order()
})
