import { jsonRPC } from './jsonrpc'

function getPageType () {
    const editBtn = $('.js-btn-edit-layout').first()
    return editBtn.data('page-type') ||
        ($('body').attr('id') === 'page-testcases-get'
            ? 'case'
            : $('body').attr('id') === 'page-testplans-get'
                ? 'plan'
                : $('body').attr('id') === 'page-testruns-get' ? 'run' : '')
}

export function ensureBlockControls () {
    const pageType = getPageType()

    $('.layout-block').each(function () {
        const block = $(this)
        const blockId = block.data('layout-block')
        const blockTitle = block.data('layout-title') || blockId
        const isDisabled = block.hasClass('layout-block-disabled-init') || block.hasClass('is-disabled')

        if (isDisabled) {
            block.addClass('is-disabled').removeClass('is-enabled')
        } else {
            block.addClass('is-enabled').removeClass('is-disabled')
        }

        if (!block.find('.layout-block-ctrl').length) {
            const ctrl = $(`
                <div class="layout-block-ctrl">
                    <button type="button" class="btn btn-xs js-layout-toggle-btn"
                            data-block-id="${blockId}" data-title="${blockTitle}" data-page-type="${pageType}">
                        <span class="fa ${isDisabled ? 'fa-eye-slash' : 'fa-eye'}"></span>
                        <span class="layout-btn-text">${blockTitle}: ${isDisabled ? 'Hidden' : 'Visible'}</span>
                    </button>
                </div>
            `)
            ctrl.find('.js-layout-toggle-btn').addClass(isDisabled ? 'btn-danger' : 'btn-primary')
            block.append(ctrl)
        }
    })
}

export function toggleLayoutEditMode (buttonEl) {
    ensureBlockControls()

    $('body').toggleClass('layout-edit-mode')
    const isEditing = $('body').hasClass('layout-edit-mode')
    const editBtn = buttonEl ? $(buttonEl) : $('.js-btn-edit-layout').first()

    if (isEditing) {
        editBtn.addClass('active btn-warning').html(
            '<i class="fa fa-check"></i> ' + (window.gettext ? gettext('Done layout editing') : 'Done layout editing')
        )
        if (!$('#layout-edit-banner').length) {
            const banner = $(`
                <div id="layout-edit-banner" class="alert alert-info kiwi-margin-top-10" style="margin-bottom: 20px;">
                    <span class="pficon pficon-info"></span>
                    <strong>${window.gettext ? gettext('Layout editing mode:') : 'Layout editing mode:'}</strong>
                    ${window.gettext ? gettext('Click on block buttons to toggle visibility. Changes apply to all pages of this type.') : 'Click on block buttons to toggle visibility. Changes apply to all pages of this type.'}
                    <button type="button" class="btn btn-primary btn-xs pull-right js-exit-layout-editor">
                        <i class="fa fa-check"></i> ${window.gettext ? gettext('Done') : 'Done'}
                    </button>
                </div>
            `)
            $('.container-cards-pf').first().prepend(banner)
        }
    } else {
        editBtn.removeClass('active btn-warning').html(
            '<i class="fa fa-th-large"></i> ' + (window.gettext ? gettext('Customize layout') : 'Customize layout')
        )
        $('#layout-edit-banner').remove()
    }
}

export function toggleBlockVisibility (buttonEl) {
    const btn = $(buttonEl)
    const block = btn.closest('.layout-block')
    const blockId = btn.data('block-id')
    const blockTitle = btn.data('title')
    const pageType = btn.data('page-type') || getPageType()
    const wasDisabled = block.hasClass('is-disabled') || (block.hasClass('layout-block-disabled-init') && !block.hasClass('is-enabled'))
    const nextVisible = wasDisabled

    if (nextVisible) {
        block.removeClass('is-disabled layout-block-disabled-init').addClass('is-enabled')
        btn.removeClass('btn-danger').addClass('btn-primary')
        btn.find('.fa').removeClass('fa-eye-slash').addClass('fa-eye')
        btn.find('.layout-btn-text').text(`${blockTitle}: Visible`)
    } else {
        block.removeClass('is-enabled').addClass('is-disabled')
        btn.removeClass('btn-primary').addClass('btn-danger')
        btn.find('.fa').removeClass('fa-eye').addClass('fa-eye-slash')
        btn.find('.layout-btn-text').text(`${blockTitle}: Hidden`)
    }

    jsonRPC('TestCase.set_layout_block_visibility', [pageType, blockId, nextVisible], function () {
        // Updated successfully
    })
}

// Global delegated handlers attached to document immediately
$(document).on('click', '.js-btn-edit-layout', function (e) {
    e.preventDefault()
    e.stopPropagation()
    toggleLayoutEditMode(this)
})

$(document).on('click', '.js-layout-toggle-btn', function (e) {
    e.preventDefault()
    e.stopPropagation()
    toggleBlockVisibility(this)
})

$(document).on('click', '.js-exit-layout-editor', function (e) {
    e.preventDefault()
    toggleLayoutEditMode($('.js-btn-edit-layout').first())
})

export function initLayoutEditor () {
    try {
        ensureBlockControls()
    } catch (err) {
        console.error('[LayoutEditor] error during init:', err)
    }
}
