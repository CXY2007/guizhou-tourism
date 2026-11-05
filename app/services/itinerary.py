from ..i18n import attr_field, city_label


def generate_itinerary(attractions, days):
    ordered = sorted(
        attractions,
        key=lambda attraction: (attraction.city or "", -float(attraction.rating or 0), attraction.id),
    )
    result = []
    for index in range(days):
        group = ordered[index * 2:index * 2 + 2]
        result.append({
            "day": index + 1,
            "morning": _item(group[0]) if group else None,
            "afternoon": _item(group[1]) if len(group) > 1 else None,
            "evening": None,
        })
    return result


def _item(attraction):
    return {
        "id": attraction.id,
        "name": attr_field(attraction, "name"),
        "slug": attraction.slug,
        "city": city_label(attraction.city),
    }
