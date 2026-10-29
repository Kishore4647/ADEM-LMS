from decimal import ROUND_HALF_UP, Decimal


def component_score(records, absence_policy: str | None):
    if not records:
        return None
    if any(r.is_absent for r in records) and absence_policy not in {"zero", "exclude"}:
        return None
    eligible = [r for r in records if not (r.is_absent and absence_policy == "exclude")]
    maximum = sum(Decimal(str(r.maximum_marks)) for r in eligible)
    if not maximum:
        return None
    obtained = sum(Decimal(str(r.obtained_marks or 0)) for r in eligible)
    return float(
        (obtained / maximum * 10).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    )


def quarterly(records, absence_policy=None):
    assessment = component_score(
        [r for r in records if r.component.value == "assessment"], absence_policy
    )
    activity = component_score(
        [r for r in records if r.component.value == "activity"], absence_policy
    )
    exams = [r for r in records if r.component.value == "quarterly_exam"]
    exam = (
        exams[0].obtained_marks if len(exams) == 1 and not exams[0].is_absent else None
    )
    total = (
        None
        if any(v is None for v in (assessment, activity, exam))
        else float(
            (
                Decimal(str(assessment)) + Decimal(str(activity)) + Decimal(str(exam))
            ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        )
    )
    return dict(
        assessment=assessment,
        activity=activity,
        exam=exam,
        total=total,
        absence_policy=absence_policy,
        complete=total is not None,
    )
