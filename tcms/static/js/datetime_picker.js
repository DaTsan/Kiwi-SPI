export function initializeDateTimePicker (selector) {
    $(selector).datetimepicker({
        locale: $('html').attr('lang'),
        format: 'YYYY-MM-DD',
        allowInputToggle: true,
        showTodayButton: true,
        tooltips: {
            today: gettext('Today'),
            clear: gettext('Clear selection'),
            close: gettext('Close'),
            selectMonth: gettext('Select month'),
            prevMonth: gettext('Previous month'),
            nextMonth: gettext('Next month'),
            selectYear: gettext('Select year'),
            prevYear: gettext('Previous year'),
            nextYear: gettext('Next year'),
            selectDecade: gettext('Select decade'),
            prevDecade: gettext('Previous decade'),
            nextDecade: gettext('Next decade'),
            prevCentury: gettext('Previous century'),
            nextCentury: gettext('Next century')
        },
        icons: {
            today: 'today-button-pf'
        }
    })
};
