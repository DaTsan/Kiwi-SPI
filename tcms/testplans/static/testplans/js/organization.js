/* Section editing and durable, atomic drag/drop of case memberships. */
let busy = false
let dragSnapshot = null
let sectionDrag = null
let currentSections = []
let permissions = {}

function manualOrder () {
    return $('.js-toolbar-sort-options .selected').data('filter-type') === 'sortkey' &&
        $('.js-toolbar-sorting-order > span:not(.hidden)').data('order') === 1 &&
        !$('#toolbar-filter').val().trim()
}

export function refreshCaseDragging () {
    const enabled = manualOrder() && !busy
    $('.js-section-testcases-list').each(function () {
        const canReorder = (permissions[$(this).data('plan-id')] || {}).reorder
        sortable(this, enabled && canReorder ? 'enable' : 'disable')
        $(this).find('.handle').attr('aria-disabled', String(!enabled || !canReorder))
    })
    $('.js-section-sort-handler').each(function () {
        const section = currentSections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
        const canReorder = canOrderSections(section)
        const disabled = busy || Boolean($('#toolbar-filter').val().trim()) || !canReorder
        $(this).toggleClass('hidden', !canReorder).attr('aria-disabled', String(disabled)).attr('draggable', String(!disabled))
    })
}

function message (text, error = false) {
    $('#case-organization-status').text(text).toggleClass('text-danger', error)
}

function request (data, success, failure) {
    if (busy) return
    busy = true
    refreshCaseDragging()
    $('.js-organization-submit').prop('disabled', true)
    message(gettext('Saving...'))
    $.ajax({
        url: $('#test_plan_pk').data('organization-url'),
        type: 'POST',
        contentType: 'application/json',
        dataType: 'json',
        headers: { 'X-CSRFToken': $('#case-organization-token input').val() },
        data: JSON.stringify(data)
    }).done(success).fail(function (response) {
        const error = response.responseJSON?.error || gettext('Could not save changes. Please try again.')
        message(error, true)
        $('.js-organization-error').text(error).removeClass('hidden')
        if (failure) failure()
    }).always(function () {
        busy = false
        $('.js-organization-submit').prop('disabled', false)
        refreshCaseDragging()
    })
}

function listFor (id) {
    return $(`#plan-section-${id} .js-section-testcases-list`)
}

function captureRows () {
    return currentSections.map(section => ({
        section: section.id,
        rows: listFor(section.id).children('.js-testcase-row').get()
    }))
}

function caseIds (rows) {
    return rows.map(row => Number(row.dataset.testcasePk))
}

function updateCounts () {
    let total = 0
    currentSections.forEach(section => {
        const container = listFor(section.id)
        const count = container.children('.js-testcase-row').length
        total += count
        container.closest('.testplan-section').find('.js-section-badge').text(count)
        container.closest('.testplan-section').find('.js-section-empty').toggleClass('hidden', count > 0)
        container.children('.js-testcase-row').attr('data-plan-id', section.id).data('plan-id', section.id)
    })
    $('.test-cases-count').text(total)
}

function saveOrder (snapshot) {
    const orders = snapshot.map(previous => ({
        section: previous.section,
        previous: caseIds(previous.rows),
        cases: caseIds(listFor(previous.section).children('.js-testcase-row').get())
    })).filter(order => JSON.stringify(order.previous) !== JSON.stringify(order.cases))
    if (!orders.length) return
    const restore = function () {
        snapshot.forEach(previous => listFor(previous.section).append(previous.rows))
        updateCounts()
    }
    if (busy) {
        restore()
        return
    }
    request({ action: 'order', orders }, function (result) {
        result.orders.forEach(order => {
            const section = currentSections.find(item => item.id === order.section)
            section.cases = order.cases.map((caseId, index) => ({ case_id: caseId, sortkey: index * 10 }))
        })
        updateCounts()
        message(gettext('Case order saved.'))
    }, restore)
}

export function bindCaseOrganization (sections) {
    currentSections = sections
    permissions = JSON.parse($('#organization-permissions').text())
    sections.forEach(section => {
        const element = $(`#plan-section-${section.id}`)
        const caps = permissions[section.id] || {}
        element.find('.js-section-add-subsection').toggleClass('hidden', !caps.create)
        element.find('.js-section-rename').toggleClass('hidden', !caps.rename)
        element.find('.js-testcase-sort-handler').toggleClass('hidden', !caps.reorder)
        sortable(listFor(section.id)[0], {
            items: '.js-testcase-row',
            handle: '.handle',
            connectWith: 'kiwi-plan-cases',
            forcePlaceholderSize: true,
            placeholderClass: 'case-sort-placeholder'
        })
    })
    $('.js-section-testcases-list').off('.organization')
        .on('sortstart.organization', function () {
            if (!dragSnapshot) dragSnapshot = captureRows()
        }).on('sortupdate.organization', function () {
            const snapshot = dragSnapshot
            dragSnapshot = null
            if (snapshot) saveOrder(snapshot)
        }).on('sortstop.organization', function () {
            setTimeout(function () { dragSnapshot = null }, 0)
        })
    $('.js-testcase-row .handle').off('.organization').on('keydown.organization', function (event) {
        if (!['ArrowUp', 'ArrowDown'].includes(event.key) || !manualOrder() || busy) return
        event.preventDefault()
        const row = $(this).closest('.js-testcase-row')
        if (!permissions[row.data('plan-id')]?.reorder) return
        const snapshot = captureRows()
        const sibling = event.key === 'ArrowUp' ? row.prev('.js-testcase-row') : row.next('.js-testcase-row')
        if (!sibling.length) return
        if (event.key === 'ArrowUp') row.insertBefore(sibling)
        else row.insertAfter(sibling)
        this.focus()
        saveOrder(snapshot)
    })
    bindSectionDragging()
    $('.js-section-add-subsection, .js-section-rename').off('.organization').on('click.organization', function () {
        const section = sections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
        const create = $(this).hasClass('js-section-add-subsection')
        const form = $('#section-editor-form')
        form.data('section', section.id).data('action', create ? 'create' : 'rename')
        $('#section-editor-title').text(create ? gettext('Add subsection') : gettext('Rename section'))
        $('#section-editor-context').text(`TP-${section.id}: ${section.name}`)
        $('#section-editor-name').val(create ? '' : section.name)
        $('#section-editor-description').val('').closest('.form-group').toggle(create)
        $('.js-organization-error').empty().addClass('hidden')
        $('#section-editor').modal('show')
    })
    $('#section-editor').off('shown.bs.modal.organization').on('shown.bs.modal.organization', function () {
        $('#section-editor-name').trigger('focus')
    })
    $('#section-editor-form').off('.organization').on('submit.organization', function (event) {
        event.preventDefault()
        request({
            action: $(this).data('action'),
            section: $(this).data('section'),
            name: $('#section-editor-name').val(),
            description: $('#section-editor-description').val()
        }, function (result) {
            window.location.hash = `plan-section-${result.section}`
            window.location.reload()
        })
    })
    bindTransfer(sections)
    refreshCaseDragging()
}

function siblingsOf (section) {
    return currentSections.filter(item => item.parent_id === section.parent_id)
}

function canOrderSections (section) {
    return section && currentSections.some(item => item.id === section.parent_id) &&
        permissions[section.parent_id]?.rename && siblingsOf(section).length > 1 &&
        siblingsOf(section).every(item => permissions[item.id]?.rename)
}

function sectionBlock (section) {
    const start = currentSections.indexOf(section)
    let end = start + 1
    while (end < currentSections.length && currentSections[end].tree_depth > section.tree_depth) end++
    return currentSections.slice(start, end)
}

function moveSection (section, target, after) {
    if (busy || !canOrderSections(section) || section.parent_id !== target.parent_id || section.id === target.id) return
    const snapshot = currentSections.slice()
    const previous = siblingsOf(section).map(item => item.id)
    const block = sectionBlock(section)
    const targetBlock = sectionBlock(target)
    const anchor = $(`#plan-section-${after ? targetBlock[targetBlock.length - 1].id : target.id}`)
    const nodes = $(block.map(item => document.getElementById(`plan-section-${item.id}`)))
    const remaining = currentSections.filter(item => !block.includes(item))
    const index = remaining.indexOf(after ? targetBlock[targetBlock.length - 1] : target) + (after ? 1 : 0)
    remaining.splice(index, 0, ...block)
    if (JSON.stringify(previous) === JSON.stringify(remaining.filter(item => item.parent_id === section.parent_id).map(item => item.id))) return
    if (after) nodes.insertAfter(anchor)
    else nodes.insertBefore(anchor)
    // Keep the shared array used by filtering and collapse/expand in DFS order.
    currentSections.splice(0, currentSections.length, ...remaining)
    const focusHandle = () => $(`#plan-section-${section.id} .js-section-sort-handler`).trigger('focus')
    focusHandle()
    request({
        action: 'section_order',
        parent: section.parent_id,
        previous,
        sections: siblingsOf(section).map(item => item.id)
    }, function () {
        const familyNode = id => $('#test-plan-family-tree a').filter(function () {
            return this.pathname.replace(/\/$/, '') === `/plan/${id}`
        }).closest('.list-group-item')
        if (after) familyNode(section.id).insertAfter(familyNode(target.id))
        else familyNode(section.id).insertBefore(familyNode(target.id))
        message(gettext('Section order saved.'))
    }, function () {
        currentSections.splice(0, currentSections.length, ...snapshot)
        $('#testcases-list').append(snapshot.map(item => document.getElementById(`plan-section-${item.id}`)))
        focusHandle()
    })
}

function clearSectionDrag () {
    sectionDrag = null
    $('.testplan-section').removeClass('section-dragging section-drop-before section-drop-after')
}

function bindSectionDragging () {
    clearSectionDrag()
    $('.js-section-sort-handler').off('.organization')
        .on('dragstart.organization', function (event) {
            if ($(this).attr('aria-disabled') === 'true') {
                event.preventDefault()
                return
            }
            sectionDrag = currentSections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
            const transfer = event.originalEvent.dataTransfer
            transfer.effectAllowed = 'move'
            transfer.setData('text/plain', String(sectionDrag.id))
            sectionBlock(sectionDrag).forEach(item => $(`#plan-section-${item.id}`).addClass('section-dragging'))
            event.stopPropagation()
        }).on('dragend.organization', clearSectionDrag)
        .on('keydown.organization', function (event) {
            if (!['ArrowUp', 'ArrowDown'].includes(event.key) || $(this).attr('aria-disabled') === 'true') return
            event.preventDefault()
            const section = currentSections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
            const siblings = siblingsOf(section)
            const after = event.key === 'ArrowDown'
            const target = siblings[siblings.indexOf(section) + (after ? 1 : -1)]
            if (target) moveSection(section, target, after)
        })
    $('.testplan-section-heading').off('.sectionOrganization')
        .on('dragover.sectionOrganization', function (event) {
            $('.testplan-section').removeClass('section-drop-before section-drop-after')
            if (!sectionDrag || busy) return
            const target = currentSections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
            if (target.id === sectionDrag.id || target.parent_id !== sectionDrag.parent_id) return
            event.preventDefault()
            event.originalEvent.dataTransfer.dropEffect = 'move'
            const bounds = this.getBoundingClientRect()
            const after = event.originalEvent.clientY > bounds.top + bounds.height / 2
            $(this).closest('.testplan-section').addClass(after ? 'section-drop-after' : 'section-drop-before')
        }).on('dragleave.sectionOrganization', function (event) {
            if (!this.contains(event.relatedTarget)) $(this).closest('.testplan-section').removeClass('section-drop-before section-drop-after')
        }).on('drop.sectionOrganization', function (event) {
            if (!sectionDrag) return
            event.preventDefault()
            const section = sectionDrag
            const target = currentSections.find(item => item.id === Number($(this).closest('.testplan-section').data('plan-id')))
            const after = $(this).closest('.testplan-section').hasClass('section-drop-after')
            clearSectionDrag()
            moveSection(section, target, after)
        })
}

function bindTransfer (sections) {
    $('#case-transfer-open').toggleClass('hidden', !Object.values(permissions).some(caps => caps.move || caps.copy))
    $('#case-transfer-open').off('.organization').on('click.organization', function () {
        const items = $('.js-testcase-row:visible input[type="checkbox"]:checked').get().map(input => ({
            section: Number($(input).closest('.js-testcase-row').data('plan-id')),
            case: Number($(input).closest('.js-testcase-row').data('testcase-pk'))
        }))
        if (!items.length) {
            message(gettext('Select test cases and a destination section.'), true)
            return
        }
        $('#case-transfer-form').data('items', items)
        const destinations = $('#case-transfer-destination').empty()
        sections.filter(section => permissions[section.id]).forEach(section => {
            $('<option>').val(section.id).text(`${'— '.repeat(section.tree_depth)}TP-${section.id}: ${section.name}`).appendTo(destinations)
        })
        $('#case-transfer-mode option[value="move"]').prop('disabled', !items.every(item => permissions[item.section]?.move))
        $('#case-transfer-mode option[value="copy"]').prop('disabled', !items.every(item => permissions[item.section]?.copy))
        $('#case-transfer-mode').val($('#case-transfer-mode option:not(:disabled)').first().val())
        $('#case-transfer-count').text(interpolate(gettext('Selected cases: %s'), [items.length]))
        $('.js-organization-error').empty().addClass('hidden')
        $('#case-transfer').modal('show')
    })
    $('#case-transfer-form').off('.organization').on('submit.organization', function (event) {
        event.preventDefault()
        request({
            action: 'transfer',
            mode: $('#case-transfer-mode').val(),
            destination: Number($('#case-transfer-destination').val()),
            items: $(this).data('items')
        }, function (result) {
            window.location.hash = `plan-section-${result.section}`
            window.location.reload()
        })
    })
}
