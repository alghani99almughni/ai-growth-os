from app.industry_catalog import DEFAULT_CATALOG, CatalogPayload


def test_default_catalog_covers_uploaded_industry_workbook():
    # Workbook contains 18 category/business-type rows.
    assert len(DEFAULT_CATALOG) == 18
    assert any(category == "Hospitality & Food Services" and business_type == "Hotels & Fine Dining"
               for category, business_type, _ in DEFAULT_CATALOG)
    assert any(category == "Healthcare & Wellness" and business_type == "Small Clinics, Dental & Diagnostics"
               for category, business_type, _ in DEFAULT_CATALOG)


def test_catalog_role_lists_are_present_and_nonempty():
    for category, business_type, roles in DEFAULT_CATALOG:
        assert category.strip()
        assert business_type.strip()
        assert roles.strip()
        assert len([role for role in roles.split(",") if role.strip()]) >= 3


def test_catalog_payload_accepts_custom_category_and_subcategory():
    payload = CatalogPayload(
        category="Local Services",
        business_type="Home Cleaning",
        roles=["Cleaner", "Supervisor"],
        is_active=True,
        sort_order=50,
    )
    assert payload.category == "Local Services"
    assert payload.business_type == "Home Cleaning"
    assert payload.roles == ["Cleaner", "Supervisor"]
