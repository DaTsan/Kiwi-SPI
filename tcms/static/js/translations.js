/* Defaults are installed before page handlers initialize their tables. */
export function initializeTranslations () {
    // PatternFly's input paginator hardcodes a label outside DataTables' language options.
    const paginator = $.fn.dataTableExt.oPagination.bootstrap_input
    const initializePaginator = paginator.fnInit
    paginator.fnInit = function (settings, paging, draw) {
        initializePaginator.call(this, settings, paging, draw)
        $(paging).find('.paginate_of').each(function () {
            this.firstChild.nodeValue = gettext('of') + ' '
        })
        $(paging).find('.paginate_input').attr('aria-label', gettext('Page'))
    }

    $.extend(true, $.fn.dataTable.defaults, {
        language: {
            emptyTable: gettext('No records found'),
            zeroRecords: gettext('No matching records found'),
            info: gettext('Showing _START_ to _END_ of _TOTAL_ entries'),
            infoEmpty: gettext('Showing 0 to 0 of 0 entries'),
            infoFiltered: gettext('(filtered from _MAX_ total entries)'),
            lengthMenu: gettext('Show _MENU_ entries'),
            loadingRecords: gettext('Loading...'),
            processing: gettext('Processing...'),
            search: gettext('Search:'),
            paginate: {
                first: gettext('First'),
                last: gettext('Last'),
                next: gettext('Next'),
                previous: gettext('Previous')
            },
            aria: {
                sortAscending: gettext(': activate to sort column ascending'),
                sortDescending: gettext(': activate to sort column descending')
            },
            select: {
                rows: {
                    _: gettext('%d rows selected'),
                    0: '',
                    1: gettext('1 row selected')
                }
            },
            buttons: {
                print: gettext('Print'),
                copy: gettext('Copy'),
                copyTitle: gettext('Copy to clipboard'),
                colvis: gettext('Column visibility')
            }
        }
    })
}
