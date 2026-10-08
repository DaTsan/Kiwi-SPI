import { jsonRPC } from '../../../../static/js/jsonrpc'
import { tagsCard } from '../../../../static/js/tags'
import {
    animate,
    advancedSearchAndAddTestCases,
    bindDeleteCommentButton, changeDropdownSelectedItem,
    markdown2HTML, renderCommentsForObject, renderCommentHTML,
    treeViewBind, quickSearchAndAddTestCase,
    findSelectorsToShowAndHide, findSelectorsToShowAndHideFromAPIData,
    showOrHideMultipleRows
} from '../../../../static/js/utils'
import { initSimpleMDE } from '../../../../static/js/simplemde_security_override'

const expandedTestCaseIds = []
const fadeAnimationTime = 500

const allTestCases = {}
const autocompleteCache = {}

let sections = []
let currentSortBy = 'sortkey'

const confirmedStatuses = []

export function pageTestplansGetReadyHandler () {
    const testPlanDataElement = $('#test_plan_pk')
    const testPlanId = testPlanDataElement.data('testplan-pk')

    const permissions = {
        'perm-change-testcase': testPlanDataElement.data('perm-change-testcase') === 'True',
        'perm-remove-testcase': testPlanDataElement.data('perm-remove-testcase') === 'True',
        'perm-add-testcase': testPlanDataElement.data('perm-add-testcase') === 'True',
        'perm-add-comment': testPlanDataElement.data('perm-add-comment') === 'True',
        'perm-delete-comment': testPlanDataElement.data('perm-delete-comment') === 'True',
        'perm-change-testcaseplan': testPlanDataElement.data('perm-change-testcaseplan') === 'True'
    }

    // bind everything in tags table
    const permRemoveTag = testPlanDataElement.data('perm-remove-tag') === 'True'
    tagsCard('TestPlan', testPlanId, { plan: testPlanId }, permRemoveTag)

    jsonRPC('TestCaseStatus.filter', { is_confirmed: true }, function (statuses) {
        // save for later use
        for (let i = 0; i < statuses.length; i++) {
            confirmedStatuses.push(statuses[i].id)
        }

        loadPlanTreeAndTestCases(testPlanId, permissions)
    })

    adjustTestPlanFamilyTree()
    collapseDocumentText()
    quickSearchAndAddTestCase(testPlanId, addTestCaseToPlan, autocompleteCache)
    $('#btn-search-cases').click(function () {
        return advancedSearchAndAddTestCases(
            testPlanId, 'TestPlan.add_case', $(this).attr('href'),
            $('#test_plan_pk').data('trans-error-adding-cases')
        )
    })
}

function loadPlanTreeAndTestCases (testPlanId, permissions) {
    jsonRPC('TestPlan.tree', [testPlanId, true], function (treeData) {
        sections = treeData
        const allCaseIdsSet = new Set()
        sections.forEach(sec => {
            if (sec.cases) {
                sec.cases.forEach(c => allCaseIdsSet.add(c.case_id))
            }
        })
        const allCaseIds = Array.from(allCaseIdsSet)

        if (allCaseIds.length > 0) {
            jsonRPC('TestCase.filter', { id__in: allCaseIds }, function (caseData) {
                caseData.forEach(tc => {
                    allTestCases[tc.id] = tc
                })
                renderAllSections(testPlanId, permissions)
                toolbarEvents(testPlanId, permissions)
            })
        } else {
            renderAllSections(testPlanId, permissions)
            toolbarEvents(testPlanId, permissions)
        }
    })
}

function addTestCaseToPlan (planId) {
    const caseName = $('#search-testcase')[0].value
    const testCase = autocompleteCache[caseName]

    // test case is already present so don't add it
    if (allTestCases[testCase.id]) {
        $('#search-testcase').val('')
        return false
    }

    jsonRPC('TestPlan.add_case', [planId, testCase.id], function (result) {
        window.location.reload(true)
        $('#search-testcase').val('')
    })
}

function collapseDocumentText () {
    const infoCardHeight = 0.59 * $('#testplan-info').height()

    if ($('#testplan-text').height() > infoCardHeight) {
        $('#testplan-text-collapse-btn').removeClass('hidden')

        $('#testplan-text').css('min-height', infoCardHeight)
        $('#testplan-text').css('height', infoCardHeight)
        $('#testplan-text').css('overflow', 'hidden')

        $('#testplan-text').on('hidden.bs.collapse', function () {
            $('#testplan-text').removeClass('collapse').css({
                height: infoCardHeight
            })
        })
    }
}

function adjustTestPlanFamilyTree () {
    treeViewBind('#test-plan-family-tree')

    // remove the > arrows from elements which don't have children
    $('#test-plan-family-tree').find('.list-group-item-container').each(function (index, element) {
        if (!element.innerHTML.trim()) {
            const span = $(element).siblings('.list-group-item-header').find('.list-view-pf-left span')

            span.removeClass('fa-angle-right')
            span.attr('style', 'width:9px')
        }
    })

    // expand all parent elements so that the current one is visible
    $('#test-plan-family-tree').find('.list-group-item.active').each(function (index, element) {
        $(element).parents('.list-group-item-container').each(function (idx, container) {
            $(container).toggleClass('hidden')
            $(container).siblings('.list-group-item-header').find('.fa-angle-right').toggleClass('fa-angle-down')
        })
    })

    // TestRail quick navigation: smooth scroll to section in unified list
    $('#test-plan-family-tree').on('click', 'a', function (e) {
        const href = $(this).attr('href')
        if (!href) return

        const match = href.match(/\/plan\/(\d+)/)
        if (match) {
            const planId = match[1]
            const targetSection = $(`#plan-section-${planId}`)

            if (targetSection.length > 0) {
                e.preventDefault()

                expandSectionAndAncestors(planId)

                // Smooth scroll to section
                $('html, body').animate({
                    scrollTop: targetSection.offset().top - 70
                }, 300)

                // Flash highlight effect
                targetSection.addClass('section-highlight')
                setTimeout(function () {
                    targetSection.removeClass('section-highlight')
                }, 1200)
            }
        }
    })
}

function renderAllSections (testPlanId, permissions) {
    const container = $('#testcases-list')
    container.empty()

    const sectionTemplate = $('#test_plan_section')[0].content
    const testCaseRowDocumentFragment = $('#test_case_row')[0].content

    let totalCasesCount = 0

    if (sections.length === 0) {
        const noCasesTemplate = $('#no_test_cases')
        container.append(noCasesTemplate[0].innerHTML)
        $('.test-cases-count').text(0)
        return
    }

    const sortOrder = getCurrentSortOrder()

    sections.forEach(section => {
        const sectionNode = $(sectionTemplate.cloneNode(true))
        const sectionEl = sectionNode.find('.testplan-section')
        sectionEl.attr('id', `plan-section-${section.id}`)
        sectionEl.attr('data-plan-id', section.id)
        sectionEl.attr('data-parent-id', section.parent_id || '')
        sectionEl.attr('data-depth', section.tree_depth)

        const depthClass = `testplan-section-depth-${Math.min(section.tree_depth, 4)}`
        sectionEl.addClass(depthClass)

        // Section title
        const titleLink = sectionNode.find('.js-section-title-link')
        titleLink.attr('href', section.url)
        const iconHtml = section.tree_depth > 0
            ? '<span class="fa fa-folder-open-o text-muted"></span> '
            : '<span class="fa fa-folder-o text-primary"></span> '
        titleLink.html(`${iconHtml}TP-${section.id}: ${section.name}`)

        // Add case buttons
        sectionNode.find('.js-section-add-new-case').attr('href', `/case/new/?from_plan=${section.id}`)
        sectionNode.find('.js-section-link-cases').attr('data-plan-id', section.id)

        // Gather test cases belonging to this section
        const sectionCases = []
        if (section.cases) {
            section.cases.forEach(c => {
                if (allTestCases[c.case_id]) {
                    const tcCopy = Object.assign({}, allTestCases[c.case_id], {
                        sortkey: c.sortkey,
                        section_plan_id: section.id
                    })
                    sectionCases.push(tcCopy)
                }
            })
        }

        sortCasesArray(sectionCases, currentSortBy, sortOrder)

        const listContainer = sectionNode.find('.js-section-testcases-list')
        listContainer.attr('data-plan-id', section.id)

        if (sectionCases.length > 0) {
            sectionCases.forEach(tc => {
                const row = getTestCaseRowContent(testCaseRowDocumentFragment.cloneNode(true), tc, permissions)
                row.attr('data-plan-id', section.id)
                listContainer.append(row)
            })
            sectionNode.find('.js-section-empty').addClass('hidden')
        } else {
            sectionNode.find('.js-section-empty').removeClass('hidden')
        }

        sectionNode.find('.js-section-badge').text(sectionCases.length)
        totalCasesCount += sectionCases.length

        container.append(sectionNode)
    })

    $('.test-cases-count').text(totalCasesCount)

    attachEvents(testPlanId, permissions)
    attachSectionEvents(testPlanId, permissions)
}

function attachSectionEvents (testPlanId, permissions) {
    $('.js-section-toggle').off('click').on('click', function (e) {
        e.stopPropagation()
        toggleSection($(this).closest('.testplan-section'))
    })

    // Header click to toggle collapse/expand
    $('.testplan-section-heading').off('click').on('click', function (e) {
        if ($(e.target).closest('input, button, a, .dropdown-menu').length) {
            return
        }
        toggleSection($(this).closest('.testplan-section'))
    })

    // Section checkbox click to toggle all cases in this section
    $('.js-section-checkbox').off('click').on('click', function (e) {
        e.stopPropagation()
        const isChecked = this.checked
        const section = $(this).closest('.testplan-section')
        section.find('.js-testcase-row:visible input[type="checkbox"]').prop('checked', isChecked)

        syncCheckboxStates()
    })

    // Link existing cases button click handler
    $('.js-section-link-cases').off('click').on('click', function (e) {
        e.preventDefault()
        const planId = $(this).data('plan-id')
        const searchUrl = $('#test_plan_pk').data('cases-search-url') || '/cases/search/'
        advancedSearchAndAddTestCases(
            planId,
            'TestPlan.add_case',
            searchUrl,
            $('#test_plan_pk').data('trans-error-adding-cases')
        )
    })
}

function toggleSection (sectionEl) {
    const body = sectionEl.find('.js-section-body')
    const toggleIcon = sectionEl.find('.js-section-toggle')

    body.toggleClass('hidden')
    if (body.hasClass('hidden')) {
        toggleIcon.removeClass('fa-angle-down').addClass('fa-angle-right')
    } else {
        toggleIcon.removeClass('fa-angle-right').addClass('fa-angle-down')
    }

    updateSubsectionsVisibility()
    syncCheckboxStates()
}

function updateSubsectionsVisibility () {
    const expandedMap = {}
    sections.forEach(sec => {
        const secEl = $(`#plan-section-${sec.id}`)
        expandedMap[sec.id] = !secEl.find('.js-section-body').hasClass('hidden')
    })

    const isSearchActive = $('#toolbar-filter').length && $('#toolbar-filter').val().trim().length > 0

    sections.forEach(sec => {
        const secEl = $(`#plan-section-${sec.id}`)
        let shouldShow = true
        let currentParentId = sec.parent_id

        while (currentParentId) {
            const parentSec = sections.find(s => s.id === currentParentId)
            if (!parentSec) break
            if (!expandedMap[parentSec.id]) {
                shouldShow = false
                break
            }
            currentParentId = parentSec.parent_id
        }

        if (shouldShow) {
            if (!isSearchActive || secEl.find('.js-testcase-row:visible').length > 0) {
                secEl.show()
            }
        } else {
            secEl.hide()
        }
    })
}

function expandSectionAndAncestors (planId) {
    let currentId = Number(planId)
    while (currentId) {
        const sec = sections.find(s => s.id === currentId)
        if (!sec) break

        const secEl = $(`#plan-section-${sec.id}`)
        const body = secEl.find('.js-section-body')
        if (body.hasClass('hidden')) {
            body.removeClass('hidden')
            secEl.find('.js-section-toggle').removeClass('fa-angle-right').addClass('fa-angle-down')
        }
        currentId = sec.parent_id
    }
    updateSubsectionsVisibility()
}

function syncCheckboxStates () {
    $('.testplan-section:visible').each(function () {
        const sec = $(this)
        const secInputs = sec.find('.js-testcase-row:visible input[type="checkbox"]')
        const secChecked = sec.find('.js-testcase-row:visible input[type="checkbox"]:checked')
        const secCb = sec.find('.js-section-checkbox')[0]
        if (secCb) {
            secCb.checked = (secInputs.length > 0 && secInputs.length === secChecked.length)
        }
    })

    const allInputs = $('.js-testcase-row:visible input[type="checkbox"]')
    const allChecked = $('.js-testcase-row:visible input[type="checkbox"]:checked')
    const toolbarCb = $('.js-checkbox-toolbar')[0]
    if (toolbarCb) {
        toolbarCb.checked = (allInputs.length > 0 && allInputs.length === allChecked.length)
    }
}

function redrawSingleRow (testCaseId, testPlanId, permissions) {
    const testCaseRowDocumentFragment = $('#test_case_row')[0].content
    const tcObj = allTestCases[testCaseId]

    $(`.js-testcase-row[data-testcase-pk=${testCaseId}]`).each(function () {
        const oldRow = $(this)
        const rowPlanId = oldRow.data('plan-id') || testPlanId
        const tcData = Object.assign({}, tcObj, { section_plan_id: rowPlanId })
        const newRow = getTestCaseRowContent(testCaseRowDocumentFragment.cloneNode(true), tcData, permissions)
        newRow.attr('data-plan-id', rowPlanId)
        oldRow.replaceWith(newRow)
    })

    expandedTestCaseIds.splice(expandedTestCaseIds.indexOf(testCaseId), 1)

    attachEvents(testPlanId, permissions)
}

function getTestCaseRowContent (rowContent, testCase, permissions) {
    const row = $(rowContent)

    row[0].firstElementChild.dataset.testcasePk = testCase.id
    if (testCase.section_plan_id) {
        row[0].firstElementChild.dataset.planId = testCase.section_plan_id
    }

    row.find('.js-test-case-link').html(`TC-${testCase.id}: ${testCase.summary}`).attr('href', `/case/${testCase.id}/`)
    row.find('.js-test-case-status').html(`${testCase.case_status__name}`)
    row.find('.js-test-case-priority').html(`${testCase.priority__value}`)
    row.find('.js-test-case-category').html(`${testCase.category__name}`)
    row.find('.js-test-case-author').html(`${testCase.author__username}`)
    row.find('.js-test-case-tester').html(`${testCase.default_tester__username || '-'}`)
    row.find('.js-test-case-reviewer').html(`${testCase.reviewer__username || '-'}`)

    // set links in kebab menu
    if (permissions['perm-change-testcase']) {
        row.find('.js-test-case-menu-edit')[0].href = `/case/${testCase.id}/edit/`
    }

    if (permissions['perm-add-testcase']) {
        row.find('.js-test-case-menu-clone')[0].href = `/cases/clone/?c=${testCase.id}`
    }

    // visual separation between confirmed and not confirmed
    if (!isTestCaseConfirmed(testCase.case_status)) {
        row.find('.list-group-item-header').addClass('bg-danger')
        row.find('.js-test-case-status-icon').addClass('fa-times')
        row.find('.js-test-case-tester-div').toggleClass('hidden')
        row.find('.js-test-case-reviewer-div').toggleClass('hidden')
    } else {
        row.find('.js-test-case-status-icon').addClass('fa-check-square')
    }

    // handle automated icon
    const automationIndicationElement = row.find('.js-test-case-automated')
    let automatedClassToRemove = 'fa-cog'

    if (testCase.is_automated) {
        automatedClassToRemove = 'fa-hand-paper-o'
    }

    automationIndicationElement.parent().attr(
        'title',
        automationIndicationElement.data(testCase.is_automated.toString())
    )
    automationIndicationElement.removeClass(automatedClassToRemove)

    const planSuffix = testCase.section_plan_id ? `-${testCase.section_plan_id}` : ''
    row.find('textarea')[0].id = `comment-for-testcase-${testCase.id}${planSuffix}`
    row.find('input[type="file"]')[0].id = `file-upload-for-testcase-${testCase.id}${planSuffix}`

    return row
}

function getTestCaseExpandArea (row, testCase, permissions) {
    markdown2HTML(testCase.text, row.find('.js-test-case-expand-text'))
    if (testCase.notes && testCase.notes.trim().length > 0) {
        row.find('.js-test-case-expand-notes').html(testCase.notes)
    }

    // draw attachments
    const uniqueDivCustomId = `js-tc-id-${testCase.id}-attachments`
    row.find('.js-test-case-expand-attachments').parent()[0].id = uniqueDivCustomId

    jsonRPC('TestCase.list_attachments', [testCase.id], function (data) {
        const ulElement = $(`#${uniqueDivCustomId} .js-test-case-expand-attachments`)

        if (data.length === 0) {
            ulElement.children().removeClass('hidden')
            return
        }

        const liElementFragment = $('#attachments-list-item')[0].content

        for (let i = 0; i < data.length; i++) {
            const liElement = liElementFragment.cloneNode(true)
            const attachmentLink = $(liElement).find('a')[0]
            attachmentLink.href = data[i].url
            attachmentLink.innerText = data[i].url.split('/').slice(-1)[0]
            ulElement.append(liElement)
        }
    })

    // load components
    const componentTemplate = row.find('.js-testcase-expand-components').find('template')[0].content
    jsonRPC('Component.filter', { cases: testCase.id }, function (result) {
        result.forEach(function (element) {
            const newComponent = componentTemplate.cloneNode(true)
            $(newComponent).find('span').html(element.name)
            row.find('.js-testcase-expand-components').append(newComponent)
        })
    })

    // load tags
    const tagTemplate = row.find('.js-testcase-expand-tags').find('template')[0].content
    jsonRPC('Tag.filter', { case: testCase.id }, function (result) {
        const uniqueTags = []

        result.forEach(function (element) {
            if (uniqueTags.indexOf(element.name) === -1) {
                uniqueTags.push(element.name)

                const newTag = tagTemplate.cloneNode(true)
                $(newTag).find('span').html(element.name)
                row.find('.js-testcase-expand-tags').append(newTag)
            }
        })
    })

    // render previous comments
    renderCommentsForObject(
        testCase.id,
        'TestCase.comments',
        'TestCase.remove_comment',
        !isTestCaseConfirmed(testCase.case_status) && permissions['perm-delete-comment'],
        row.find('.comments')
    )

    // render comments form
    const commentFormTextArea = row.find('.js-comment-form-textarea')
    if (!isTestCaseConfirmed(testCase.case_status) && permissions['perm-add-comment']) {
        const textArea = row.find('textarea')[0]
        const fileUpload = row.find('input[type="file"]')
        const editor = initSimpleMDE(textArea, $(fileUpload), textArea.id)

        row.find('.js-post-comment').click(function (event) {
            event.preventDefault()
            const input = editor.value().trim()

            if (input) {
                jsonRPC('TestCase.add_comment', [testCase.id, input], comment => {
                    editor.value('')

                    row.find('.comments').append(
                        renderCommentHTML(
                            1 + row.find('.js-comment-container').length,
                            comment,
                            $('template#comment-template')[0],
                            function (parentNode) {
                                bindDeleteCommentButton(
                                    testCase.id,
                                    'TestCase.remove_comment',
                                    permissions['perm-delete-comment'],
                                    parentNode)
                            })
                    )
                })
            }
        })
    } else {
        commentFormTextArea.hide()
    }
}

function attachEvents (testPlanId, permissions) {
    treeViewBind('.js-section-testcases-list')

    if (permissions['perm-change-testcase']) {
        // update default tester
        $('.js-test-case-menu-tester').off('click').click(function (ev) {
            $(this).parents('.dropdown').toggleClass('open')

            const emailOrUsername = window.prompt($('#test_plan_pk').data('trans-username-email-prompt'))
            if (!emailOrUsername) {
                return false
            }

            updateTestCasesViaAPI([getCaseIdFromEvent(ev)], { default_tester: emailOrUsername },
                testPlanId, permissions)

            return false
        })

        $('.js-test-case-menu-priority').off('click').click(function (ev) {
            $(this).parents('.dropdown').toggleClass('open')

            updateTestCasesViaAPI([getCaseIdFromEvent(ev)], { priority: ev.target.dataset.id },
                testPlanId, permissions)
            return false
        })

        $('.js-test-case-menu-status').off('click').click(function (ev) {
            $(this).parents('.dropdown').toggleClass('open')
            const testCaseId = getCaseIdFromEvent(ev)
            updateTestCasesViaAPI([testCaseId], { case_status: ev.target.dataset.id },
                testPlanId, permissions)
            return false
        })
    }

    if (permissions['perm-remove-testcase']) {
        // delete testcase from the section's plan
        $('.js-test-case-menu-delete').off('click').click(function (ev) {
            $(this).parents('.dropdown').toggleClass('open')
            const row = $(ev.target).closest('.js-testcase-row')
            const testCaseId = getCaseIdFromEvent(ev)
            const rowPlanId = row.data('plan-id') || testPlanId

            jsonRPC('TestPlan.remove_case', [rowPlanId, testCaseId], function () {
                const section = sections.find(s => s.id === rowPlanId)
                if (section && section.cases) {
                    const idx = section.cases.findIndex(c => c.case_id === testCaseId)
                    if (idx > -1) {
                        section.cases.splice(idx, 1)
                    }
                }

                row.fadeOut(fadeAnimationTime, function () {
                    const parentSection = $(this).closest('.testplan-section')
                    $(this).remove()

                    const remaining = parentSection.find('.js-testcase-row').length
                    parentSection.find('.js-section-badge').text(remaining)
                    if (remaining === 0) {
                        parentSection.find('.js-section-empty').removeClass('hidden')
                    }
                })

                const testCasesCountEl = $('.test-cases-count')
                const count = parseInt(testCasesCountEl.text()) || 0
                testCasesCountEl.text(Math.max(0, count - 1))
            })

            return false
        })
    }

    // get details and draw expand area only on expand
    $('.js-testcase-row').off('click').click(function (ev) {
        if ($(ev.target).is('button, a, input, .fa-ellipsis-v')) {
            return
        }

        const testCaseId = getCaseIdFromEvent(ev)

        if (expandedTestCaseIds.indexOf(testCaseId) > -1) {
            return
        }

        const tcRow = $(ev.target).closest(`[data-testcase-pk=${testCaseId}]`)
        expandedTestCaseIds.push(testCaseId)
        getTestCaseExpandArea(tcRow, allTestCases[testCaseId], permissions)
    })

    const inputs = $('.js-testcase-row').find('input[type="checkbox"]')
    inputs.off('click').click(function (ev) {
        ev.stopPropagation()
        syncCheckboxStates()
    })

    function getCaseIdFromEvent (ev) {
        return $(ev.target).closest('.js-testcase-row').data('testcase-pk')
    }
}

function updateTestCasesViaAPI (testCaseIds, updateQuery, testPlanId, permissions) {
    testCaseIds.forEach(function (caseId) {
        jsonRPC('TestCase.update', [caseId, updateQuery], function (updatedTC) {
            const sortkey = (allTestCases[caseId] && allTestCases[caseId].sortkey) || 0
            allTestCases[caseId] = updatedTC
            allTestCases[caseId].sortkey = sortkey

            const testCaseRows = $(`.js-testcase-row[data-testcase-pk=${caseId}]`)
            animate(testCaseRows, function () {
                redrawSingleRow(caseId, testPlanId, permissions)
            })
        })
    })
}

function getCurrentSortOrder () {
    const activeOrderIcon = $('.js-toolbar-sorting-order > span:not(.hidden)')
    return activeOrderIcon.length ? activeOrderIcon.data('order') : 1
}

function sortCasesArray (casesArray, sortBy, sortOrder) {
    casesArray.sort(function (tc1, tc2) {
        const value1 = tc1[sortBy] !== undefined && tc1[sortBy] !== null ? tc1[sortBy] : ''
        const value2 = tc2[sortBy] !== undefined && tc2[sortBy] !== null ? tc2[sortBy] : ''

        if (Number.isInteger(value1) && Number.isInteger(value2)) {
            return (value1 - value2) * sortOrder
        }

        return value1.toString().localeCompare(value2.toString()) * sortOrder
    })
}

function sortAllSections (permissions) {
    const sortBy = $('.js-toolbar-sort-options .selected')[0].dataset.filterType
    const sortOrder = getCurrentSortOrder()
    currentSortBy = sortBy

    sections.forEach(function (section) {
        const sectionEl = $(`#plan-section-${section.id}`)
        const listContainer = sectionEl.find('.js-section-testcases-list')
        const rows = listContainer.children('.js-testcase-row').get()

        rows.sort(function (a, b) {
            const pkA = $(a).data('testcase-pk')
            const pkB = $(b).data('testcase-pk')
            const tcA = allTestCases[pkA] || {}
            const tcB = allTestCases[pkB] || {}

            let valA = tcA[sortBy]
            let valB = tcB[sortBy]

            if (sortBy === 'sortkey') {
                const ca = (section.cases || []).find(c => c.case_id === pkA)
                const cb = (section.cases || []).find(c => c.case_id === pkB)
                valA = ca ? ca.sortkey : 0
                valB = cb ? cb.sortkey : 0
            }

            valA = valA !== undefined && valA !== null ? valA : ''
            valB = valB !== undefined && valB !== null ? valB : ''

            if (Number.isInteger(valA) && Number.isInteger(valB)) {
                return (valA - valB) * sortOrder
            }

            return valA.toString().localeCompare(valB.toString()) * sortOrder
        })

        $.each(rows, function (idx, item) {
            listContainer.append(item)
        })
    })
}

function toolbarEvents (testPlanId, permissions) {
    $('.js-checkbox-toolbar').off('click').click(function (ev) {
        const isChecked = ev.target.checked
        $('.js-testcase-row:visible input[type="checkbox"]').prop('checked', isChecked)
        $('.js-section-checkbox').prop('checked', isChecked)
    })

    $('.js-toolbar-filter-options li').off('click').click(function (ev) {
        return changeDropdownSelectedItem(
            '.js-toolbar-filter-options',
            '#input-filter-button',
            ev.target,
            $('#toolbar-filter')
        )
    })

    $('#toolbar-filter').off('keyup').on('keyup', function () {
        const filterValue = $(this).val().toLowerCase()
        const filterBy = $('.js-toolbar-filter-options .selected')[0].dataset.filterType

        filterTestCasesByProperty(
            testPlanId,
            Object.values(allTestCases),
            filterBy,
            filterValue
        )
    })

    $('.js-toolbar-sort-options li').off('click').click(function (ev) {
        changeDropdownSelectedItem('.js-toolbar-sort-options', '#sort-button', ev.target)
        sortAllSections(permissions)
        return false
    })

    // handle asc desc icon
    $('.js-toolbar-sorting-order > span').off('click').click(function (ev) {
        const icon = $(this)
        icon.siblings('.hidden').removeClass('hidden')
        icon.addClass('hidden')

        sortAllSections(permissions)
    })

    // sortable list per section
    sections.forEach(function (section) {
        sortable(`#plan-section-${section.id} .js-section-testcases-list`, {
            handle: '.handle',
            itemSerializer: (serializedItem) => {
                return parseInt(serializedItem.node.getAttribute('data-testcase-pk'))
            }
        })
    })

    $('.js-toolbar-manual-sort').off('click').click(function () {
        $(this).blur()
        const sortIcon = $(this).find('span')
        sortIcon.toggleClass(['fa-sort', 'fa-check-square'])
        $('.js-testcase-sort-handler, .js-testcase-expand-arrow, .js-testcase-checkbox').toggleClass('hidden')

        // If closing manual sort mode, save order for each section
        if (sortIcon.hasClass('fa-sort')) {
            sections.forEach(function (section) {
                const listEl = $(`#plan-section-${section.id} .js-section-testcases-list`)
                const serialized = sortable(listEl, 'serialize')
                if (serialized && serialized.length && serialized[0].items) {
                    const currentOrder = serialized[0].items
                    currentOrder.forEach(function (tcPk, index) {
                        jsonRPC('TestPlan.update_case_order', [section.id, tcPk, index * 10], function () {})
                    })
                }
            })
        }
    })

    $('.js-toolbar-priority').off('click').click(function (ev) {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedCases = getSelectedTestCases()

        if (!selectedCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        updateTestCasesViaAPI(selectedCases, { priority: ev.target.dataset.id },
            testPlanId, permissions)

        return false
    })

    $('.js-toolbar-status').off('click').click(function (ev) {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedCases = getSelectedTestCases()

        if (!selectedCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        updateTestCasesViaAPI(selectedCases, { case_status: ev.target.dataset.id },
            testPlanId, permissions)
        return false
    })

    $('#default-tester-button').off('click').click(function (ev) {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedCases = getSelectedTestCases()

        if (!selectedCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        const emailOrUsername = window.prompt($('#test_plan_pk').data('trans-username-email-prompt'))

        if (!emailOrUsername) {
            return false
        }

        updateTestCasesViaAPI(selectedCases, { default_tester: emailOrUsername },
            testPlanId, permissions)

        return false
    })

    $('#bulk-reviewer-button').off('click').click(function (ev) {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedCases = getSelectedTestCases()

        if (!selectedCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        const emailOrUsername = window.prompt($('#test_plan_pk').data('trans-username-email-prompt'))

        if (!emailOrUsername) {
            return false
        }

        updateTestCasesViaAPI(selectedCases, { reviewer: emailOrUsername },
            testPlanId, permissions)

        return false
    })

    $('#delete_button').off('click').click(function (ev) {
        $(this).parents('.dropdown').toggleClass('open')
        const checkedRows = $('.js-testcase-row:visible input:checked').closest('.js-testcase-row')

        if (!checkedRows.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        const areYouSureText = $('#test_plan_pk').data('trans-are-you-sure')
        if (confirm(areYouSureText)) {
            checkedRows.each(function () {
                const row = $(this)
                const testCaseId = row.data('testcase-pk')
                const rowPlanId = row.data('plan-id') || testPlanId

                jsonRPC('TestPlan.remove_case', [rowPlanId, testCaseId], function () {
                    const section = sections.find(s => s.id === rowPlanId)
                    if (section && section.cases) {
                        const idx = section.cases.findIndex(c => c.case_id === testCaseId)
                        if (idx > -1) {
                            section.cases.splice(idx, 1)
                        }
                    }

                    row.fadeOut(fadeAnimationTime, function () {
                        const parentSection = $(this).closest('.testplan-section')
                        $(this).remove()
                        const remaining = parentSection.find('.js-testcase-row').length
                        parentSection.find('.js-section-badge').text(remaining)
                        if (remaining === 0) {
                            parentSection.find('.js-section-empty').removeClass('hidden')
                        }
                    })
                })
            })

            const testCasesCountEl = $('.test-cases-count')
            const count = parseInt(testCasesCountEl.text()) || 0
            testCasesCountEl.text(Math.max(0, count - checkedRows.length))
        }

        return false
    })

    $('#bulk-clone-button').off('click').click(function () {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedCases = getSelectedTestCases()

        if (!selectedCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        window.location.assign(`/cases/clone?c=${selectedCases.join('&c=')}`)
    })

    $('#testplan-toolbar-newrun').off('click').click(function () {
        $(this).parents('.dropdown').toggleClass('open')
        const selectedTestCases = getSelectedTestCases()

        if (!selectedTestCases.length) {
            alert($('#test_plan_pk').data('trans-no-testcases-selected'))
            return false
        }

        for (let i = 0; i < selectedTestCases.length; i++) {
            const status = allTestCases[selectedTestCases[i]].case_status
            if (!isTestCaseConfirmed(status)) {
                alert($('#test_plan_pk').data('trans-cannot-create-testrun'))
                return false
            }
        }

        const newTestRunUrl = $('#test_plan_pk').data('new-testrun-url')
        window.location.assign(`${newTestRunUrl}?c=${selectedTestCases.join('&c=')}`)
        return false
    })
}

function isTestCaseConfirmed (status) {
    return confirmedStatuses.indexOf(Number(status)) > -1
}

function getSelectedTestCases () {
    const inputs = $('.js-testcase-row input:checked')
    const tcIds = []

    inputs.each(function (index, el) {
        const elJq = $(el)

        if (elJq.is(':hidden')) {
            return
        }

        const id = elJq.closest('.js-testcase-row').data('testcase-pk')
        if (id && tcIds.indexOf(id) === -1) {
            tcIds.push(id)
        }
    })

    return tcIds
}

function filterTestCasesByProperty (planId, testCases, filterBy, filterValue) {
    if (filterValue.trim().length === 0) {
        $('.testplan-section').show()
        $('.js-testcase-row').show()
        updateAllSectionBadges()
        $('.test-cases-count').text(testCases.length)
        updateSubsectionsVisibility()
        return
    }

    if (filterBy === 'component' || filterBy === 'tag') {
        const caseIds = testCases.map(tc => tc.id)
        const query = { id__in: caseIds }
        query[`${filterBy}__name__icontains`] = filterValue

        jsonRPC('TestCase.filter', query, function (filtered) {
            $('.js-testcase-row').hide()
            const rows = findSelectorsToShowAndHideFromAPIData(testCases, filtered, '[data-testcase-pk={0}]')
            showOrHideMultipleRows('.js-testcase-row', rows)
            updateSectionVisibilityAfterFilter()
            $('.test-cases-count').text(rows.show.length)
        })
    } else {
        $('.js-testcase-row').hide()
        const rows = findSelectorsToShowAndHide(testCases, filterBy, filterValue, '[data-testcase-pk={0}]')
        showOrHideMultipleRows('.js-testcase-row', rows)
        updateSectionVisibilityAfterFilter()
        $('.test-cases-count').text(rows.show.length)
    }
}

function updateSectionVisibilityAfterFilter () {
    $('.testplan-section').each(function () {
        const sec = $(this)
        const visibleCount = sec.find('.js-testcase-row:visible').length
        sec.find('.js-section-badge').text(visibleCount)

        if (visibleCount === 0) {
            sec.hide()
        } else {
            sec.show()
            const body = sec.find('.js-section-body')
            if (body.hasClass('hidden')) {
                body.removeClass('hidden')
                sec.find('.js-section-toggle').removeClass('fa-angle-right').addClass('fa-angle-down')
            }
        }
    })
}

function updateAllSectionBadges () {
    $('.testplan-section').each(function () {
        const sec = $(this)
        const total = sec.find('.js-testcase-row').length
        sec.find('.js-section-badge').text(total)
    })
}
