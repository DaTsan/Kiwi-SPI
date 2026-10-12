"""Atomic case organization within a plan's section tree."""

from collections import Counter
from operator import attrgetter

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import assign_perm

from tcms.testcases.models import Property, TestCasePlan
from tcms.testplans.models import TestPlan


class OrganizationConflict(ValidationError):
    pass


def allowed(user, permission, obj=None):
    return user.is_authenticated and (
        user.has_perm(permission)
        or (obj is not None and user.has_perm(permission, obj))
    )


def require(user, permission, obj=None):
    if not allowed(user, permission, obj):
        raise PermissionDenied


def section_permissions(user, section):
    return {
        "create": allowed(user, "testplans.add_testplan")
        and allowed(user, "testplans.change_testplan", section),
        "rename": allowed(user, "testplans.change_testplan", section),
        "reorder": allowed(user, "testcases.change_testcaseplan"),
        "move": allowed(user, "testcases.delete_testcaseplan")
        and allowed(user, "testcases.add_testcaseplan"),
        "copy": allowed(user, "testcases.add_testcase")
        and allowed(user, "testcases.add_testcaseplan"),
    }


def integer(value):
    if type(value) is not int or value < 1:
        raise ValidationError(_("Invalid section or test case ID."))
    return value


def ids(values):
    if not isinstance(values, list) or len(values) > 10000:
        raise ValidationError(_("Invalid case order."))
    values = [integer(value) for value in values]
    if len(values) != len(set(values)):
        raise ValidationError(_("A case can appear only once in a section."))
    return values


def _sections(user, root, section_ids):
    descendants = set(root.descendants(include_self=True).values_list("pk", flat=True))
    if not set(section_ids) <= descendants:
        raise ValidationError(_("Choose a section within the current plan."))
    records = {
        section.pk: section
        for section in TestPlan.objects.select_for_update()
        .filter(pk__in=section_ids)
        .order_by("pk")
    }
    if len(records) != len(set(section_ids)):
        raise ValidationError(_("The section no longer exists. Refresh the page."))
    for section in records.values():
        require(user, "testplans.view_testplan", section)
        if section.product_id != root.product_id:
            raise ValidationError(_("Sections must belong to the same product."))
    return records


def _text(data, key, limit, required=False):
    value = data.get(key, "")
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (required and not value.strip())
    ):
        raise ValidationError(_("Enter a valid section name and description."))
    return value.strip()


def confirmed_tree_cases(user, root):
    """Confirmed cases in tree order, once per case, with access checks."""
    sections = list(root.descendants(include_self=True))
    for section in sections:
        require(user, "testplans.view_testplan", section)
        if section.product_id != root.product_id:
            raise ValidationError(_("Sections must belong to the same product."))
    positions = {section.pk: index for index, section in enumerate(sections)}
    links = list(
        TestCasePlan.objects.filter(
            plan_id__in=positions, case__case_status__is_confirmed=True
        )
        .select_related("case__category")
        .order_by("sortkey", "case_id")
    )
    links.sort(key=lambda link: positions[link.plan_id])
    cases = {}
    for link in links:
        require(user, "testcases.view_testcase", link.case)
        if link.case.category.product_id != root.product_id:
            raise ValidationError(_("The test case belongs to another product."))
        cases.setdefault(link.case_id, link.case)
    return list(cases.values())


@transaction.atomic
def organize(user, root_id, data):
    root = get_object_or_404(TestPlan, pk=root_id)
    require(user, "testplans.view_testplan", root)
    if not isinstance(data, dict):
        raise ValidationError(_("Invalid organization request."))
    action = data.get("action")
    if action in ("create", "rename"):
        section_id = integer(data.get("section"))
        section = _sections(user, root, [section_id])[section_id]
        require(user, "testplans.change_testplan", section)
        name = _text(data, "name", 255, required=True)
        if action == "create":
            require(user, "testplans.add_testplan")
            section = TestPlan(
                name=name,
                text=_text(data, "description", 50000),
                parent=section,
                product_id=section.product_id,
                product_version_id=section.product_version_id,
                type_id=section.type_id,
                author=user,
            )
            section._history_user = user
            section.full_clean()
            section.save()
            for permission in ("view_testplan", "change_testplan"):
                if not user.has_perm(f"testplans.{permission}"):
                    assign_perm(permission, user, section)
        else:
            section.name = name
            section._history_user = user
            section.full_clean()
            section.save()
        return {"section": section.pk}
    if action == "order":
        return _order(user, root, data.get("orders"))
    if action == "section_order":
        return _section_order(user, root, data)
    if action == "transfer":
        return _transfer(user, root, data)
    raise ValidationError(_("Invalid organization request."))


def _section_order(user, root, data):
    parent_id = integer(data.get("parent"))
    require(
        user, "testplans.change_testplan", _sections(user, root, [parent_id])[parent_id]
    )
    submitted = []
    for key in ("previous", "sections"):
        values = data.get(key)
        if not isinstance(values, list) or len(values) > 10000:
            raise ValidationError(_("Invalid section order."))
        values = list(map(integer, values))
        if len(values) != len(set(values)):
            raise ValidationError(_("Invalid section order."))
        submitted.append(values)
    previous, new = submitted  # pylint: disable=unbalanced-tuple-unpacking
    # Lock the parent first, as subsection creation does, then its children in
    # primary-key order. Never reparent nodes or update case memberships here.
    children = list(
        TestPlan.objects.select_for_update().filter(parent_id=parent_id).order_by("pk")
    )
    for section in children:
        require(user, "testplans.view_testplan", section)
        require(user, "testplans.change_testplan", section)
        if section.product_id != root.product_id:
            raise ValidationError(_("Sections must belong to the same product."))
    current = list(
        map(attrgetter("pk"), sorted(children, key=attrgetter("position", "pk")))
    )
    if current != previous:
        raise OrganizationConflict(
            _("The section list has changed. Refresh the page and try again.")
        )
    if set(current) != set(new):
        raise ValidationError(_("The new order must preserve all sibling sections."))
    by_id = {section.pk: section for section in children}
    for index, section_id in enumerate(new, start=1):
        section = by_id[section_id]
        if section.position != index * 10:
            section.position = index * 10
            section._history_user = user  # pylint: disable=protected-access
            section.save(update_fields=["position"])
    return {"parent": parent_id, "sections": new}


def _links(section_ids):
    return list(
        TestCasePlan.objects.select_for_update()
        .filter(plan_id__in=section_ids)
        .select_related("case__category")
        .order_by("sortkey", "case_id")
    )


def _order(user, root, orders):
    if not isinstance(orders, list) or not 1 <= len(orders) <= 2:
        raise ValidationError(_("Invalid case order."))
    submitted = {}
    for order in orders:
        if not isinstance(order, dict):
            raise ValidationError(_("Invalid case order."))
        section_id = integer(order.get("section"))
        if section_id in submitted:
            raise ValidationError(_("Invalid case order."))
        submitted[section_id] = (ids(order.get("previous")), ids(order.get("cases")))
    sections = _sections(user, root, submitted)
    links = _links(sections)
    by_section = {pk: [link for link in links if link.plan_id == pk] for pk in sections}
    for pk, (previous, _new) in submitted.items():
        if [link.case_id for link in by_section[pk]] != previous:
            raise OrganizationConflict(
                _("The case list has changed. Refresh the page and try again.")
            )
    before = Counter(link.case_id for link in links)
    after = Counter(case_id for _previous, new in submitted.values() for case_id in new)
    if before != after:
        raise ValidationError(_("The new order must preserve all test cases."))
    cases = {link.case_id: link.case for link in links}
    changed, added, removed = [], [], []
    for pk, (_previous, new) in submitted.items():
        own = {link.case_id: link for link in by_section[pk]}
        retained = set(new)
        for position, case_id in enumerate(new):
            case = cases[case_id]
            require(user, "testcases.view_testcase", case)
            if case_id in own:
                require(user, "testcases.change_testcaseplan", own[case_id])
                own[case_id].sortkey = position * 10
                changed.append(own[case_id])
            else:
                require(user, "testcases.add_testcaseplan")
                if case.category.product_id != sections[pk].product_id:
                    raise ValidationError(
                        _("The test case belongs to another product.")
                    )
                added.append(
                    TestCasePlan(plan_id=pk, case_id=case_id, sortkey=position * 10)
                )
        for case_id, link in own.items():
            if case_id not in retained:
                require(user, "testcases.delete_testcaseplan", link)
                removed.append(link.pk)
    TestCasePlan.objects.filter(pk__in=removed).delete()
    TestCasePlan.objects.bulk_update(changed, ["sortkey"])
    TestCasePlan.objects.bulk_create(added)
    return {
        "orders": [
            {"section": pk, "cases": new} for pk, (_old, new) in submitted.items()
        ]
    }


def _transfer(user, root, data):
    mode, items = data.get("mode"), data.get("items")
    if (
        mode not in ("move", "copy")
        or not isinstance(items, list)
        or not 1 <= len(items) <= 1000
    ):
        raise ValidationError(_("Select test cases and a destination section."))
    pairs = []
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError(_("Invalid organization request."))
        pairs.append((integer(item.get("section")), integer(item.get("case"))))
    if len(set(pairs)) != len(pairs):
        raise ValidationError(_("Invalid organization request."))
    destination_id = integer(data.get("destination"))
    sections = _sections(user, root, {destination_id, *(pk for pk, _case in pairs)})
    destination = sections[destination_id]
    require(user, "testcases.add_testcaseplan")
    if mode == "copy":
        require(user, "testcases.add_testcase")
    links = _links(sections)
    by_pair = {(link.plan_id, link.case_id): link for link in links}
    cases = {}
    for pair in pairs:
        if pair not in by_pair:
            raise OrganizationConflict(
                _("The case list has changed. Refresh the page and try again.")
            )
        link = by_pair[pair]
        require(user, "testcases.view_testcase", link.case)
        if mode == "move":
            require(user, "testcases.delete_testcaseplan", link)
        if link.case.category.product_id != destination.product_id:
            raise ValidationError(_("The test case belongs to another product."))
        cases[link.case_id] = link.case
    next_order = (
        max(
            (link.sortkey or 0 for link in links if link.plan_id == destination_id),
            default=-10,
        )
        + 10
    )
    result = []
    for case in cases.values():
        if mode == "copy":
            copied = case.clone(new_author=user, test_plans=[destination])
            Property.objects.bulk_create(
                [
                    Property(case=copied, name=prop.name, value=prop.value)
                    for prop in Property.objects.filter(case=case)
                ]
            )
            TestCasePlan.objects.filter(plan=destination, case=copied).update(
                sortkey=next_order
            )
            result.append(copied.pk)
            next_order += 10
        else:
            if (destination_id, case.pk) not in by_pair:
                destination.add_case(case, next_order)
                next_order += 10
            result.append(case.pk)
    if mode == "move":
        TestCasePlan.objects.filter(
            pk__in=[by_pair[pair].pk for pair in pairs if pair[0] != destination_id]
        ).delete()
    return {"cases": result, "section": destination_id}
