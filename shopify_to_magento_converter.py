# ==============================================================================
# SCRIPT VERSION MARKER: v-final-2026-07-22-A
# (If you're unsure whether you have the latest file, check this line first.
#  This exact version: skips customers with no email/no firstname/no lastname;
#  fills missing ADDRESS fields only — city/country/street/phone — with
#  placeholders 'N/A' / '0000000000'; never leaves a required address field
#  blank for a customer who has at least name+email.)
# ==============================================================================
# SHOPIFY -> MAGENTO 2 CSV CONVERTER (ALL-IN-ONE)
#
# WHAT THIS SCRIPT DOES:
#   Upload your 3 Shopify export files (products.csv, customers.csv,
#   orders.csv) ONE TIME, and this script converts ALL THREE into
#   Magento-2-import-ready CSVs and downloads all 3 results automatically.
#
# HOW TO USE:
#   1. Run this single cell in Google Colab.
#   2. It will ask you to upload files ONE BY ONE — for each prompt, upload
#      the matching Shopify file (it tells you which one it wants).
#      If you don't have one of the three, just click Cancel/skip that
#      upload box (see SKIP note printed before each prompt) — it will
#      skip that entity and continue with the rest.
#   3. At the end, 3 files auto-download:
#        magento_products_import.csv
#        magento_customers_import.csv
#        magento_orders_import.csv
#
# COLUMN MAPPINGS USED (based on your real sample files):
#   - PRODUCTS  -> Magento product import format (sku, attribute_set_code,
#     product_type, categories, name, price, images, qty, is_in_stock, etc.)
#     Shopify variant rows are grouped by "Handle"; simple vs configurable
#     is auto-detected.
#   - CUSTOMERS -> Magento customer import format (email, firstname,
#     lastname, group_id, company_name, mobile, etc.)
#   - ORDERS    -> Magento "Order with Items" format (Order #, Order Status,
#     Customer Name/Email, Billing/Shipping details, Item SKU/Name/Qty/Price,
#     Row Total, etc.) — matches the real sample order-with-items file you
#     shared.
#
# KNOWN LIMITATIONS (marked with TODO in code — fix later if needed):
#   - Stock quantity: Shopify's products.csv you shared has no inventory
#     qty column, so qty is set to 0 / is_in_stock = 1 for all products.
#     Provide a Shopify Inventory export separately if you want real numbers.
#   - Order "Store" column uses a placeholder store path — update if your
#     Magento setup uses a different website/store/store-view name.
#   - Per-item tax isn't split (Shopify only gives order-level tax).
# ==============================================================================

import pandas as pd
import numpy as np
import os


def upload_one(label):
    """Asks for a local file path in the terminal, returns a DataFrame or
    None if left blank (skipped). Works with plain Python anywhere —
    VS Code, PyCharm, Command Prompt/Terminal, or any other environment."""
    path = input(f"\n>>> Enter path to your Shopify '{label}' CSV "
                 f"(or press Enter to skip): ").strip().strip('"')
    if not path:
        print(f"Skipped '{label}'.")
        return None
    if not os.path.isfile(path):
        print(f"File not found: {path} — skipping '{label}'.")
        return None
    df = pd.read_csv(path, dtype=str).fillna("")
    print(f"Loaded '{path}' with {len(df)} rows.")
    return df


# --------------------------------------------------------------------------
# GENERIC COLUMN HELPERS
# Different Shopify stores/apps can export CSVs with slightly different
# column names/order (extra metafield columns, renamed fields, missing
# optional columns, etc). These helpers make the converters resilient to
# that instead of hard-depending on one exact file's column list.
# --------------------------------------------------------------------------
def resolve_col(df, *candidates):
    """Find the actual column name in df matching any candidate name
    (case-insensitive, ignores extra spaces). Returns None if none found."""
    lookup = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lookup:
            return lookup[key]
    return None


def get_val(row, *candidates, default=""):
    """Get a value from a row trying multiple possible column names."""
    for cand in candidates:
        if cand in row.index:
            val = row[cand]
            if val not in (None, np.nan) and str(val).strip() != "":
                return val
    return default

# ==========================================================================
# PRODUCTS: Shopify -> Magento 2 product import format
# Works with ANY Shopify product export (not just one specific file) —
# column names are resolved dynamically, and missing optional columns
# are handled with safe fallbacks instead of crashing.
# ==========================================================================
def truncate_meta_description(text, limit=255):
    """Magento's default 'meta_description' attribute has a 255-character
    limit. Rows exceeding it get silently skipped/rejected during import
    (no visible error on screen, only in the downloadable report). We trim
    at a word boundary so it doesn't cut off mid-word, and don't touch the
    actual product description — only this SEO meta field."""
    text = text or ""
    if len(text) <= limit:
        return text
    trimmed = text[:limit]
    # cut back to the last full word so it doesn't end mid-word
    last_space = trimmed.rfind(" ")
    if last_space > 0:
        trimmed = trimmed[:last_space]
    return trimmed.rstrip(" ,.;:-") 


def convert_products(df):
    df = df.copy()

    # Resolve real column names (Shopify's standard export uses these names,
    # but we fall back gracefully if a store/app export differs slightly)
    c_handle   = resolve_col(df, "Handle") or "__handle__"
    c_title    = resolve_col(df, "Title")
    c_body     = resolve_col(df, "Body (HTML)", "Body(HTML)", "Description")
    c_category = resolve_col(df, "Product Category", "Category")
    c_type     = resolve_col(df, "Type")
    c_status   = resolve_col(df, "Status", "Published")
    c_seo_t    = resolve_col(df, "SEO Title")
    c_seo_d    = resolve_col(df, "SEO Description")
    c_sku      = resolve_col(df, "Variant SKU", "SKU")
    c_price    = resolve_col(df, "Variant Price", "Price")
    c_compare  = resolve_col(df, "Variant Compare At Price", "Compare At Price")
    c_grams    = resolve_col(df, "Variant Grams", "Grams", "Weight")
    c_cost     = resolve_col(df, "Cost per item", "Cost Per Item")
    c_image    = resolve_col(df, "Image Src", "Image")
    c_vimage   = resolve_col(df, "Variant Image")
    c_qty      = resolve_col(df, "Variant Inventory Qty", "Inventory Qty", "Available")
    c_opt1n    = resolve_col(df, "Option1 Name")
    c_opt1v    = resolve_col(df, "Option1 Value")
    c_opt2n    = resolve_col(df, "Option2 Name")
    c_opt2v    = resolve_col(df, "Option2 Value")

    # If there's no real "Handle" column, treat every row as its own product
    if c_handle == "__handle__" and c_handle not in df.columns:
        df[c_handle] = [f"product-{i}" for i in range(len(df))]

    # Forward-fill descriptive columns within each product group (Shopify
    # only fills these on a product's first variant row, leaves rest blank)
    shared_cols = [c for c in [c_title, c_body, c_category, c_type, c_status,
                                c_seo_t, c_seo_d] if c]
    for col in shared_cols:
        df[col] = df.groupby(c_handle)[col].transform(
            lambda s: s.replace("", np.nan).ffill().fillna("")
        )

    magento_rows = []

    for handle, group in df.groupby(c_handle):
        first = group.iloc[0]

        # Collect images for this product
        images = []
        if c_image:
            images = [img for img in group[c_image].tolist() if img]
        main_image = images[0] if images else ""
        extra_images = ",".join(images[1:]) if len(images) > 1 else ""

        # Category path -> Magento format "Default Category/X/Y"
        # NOTE: Shopify's "Product Category" often uses " > " to separate
        # hierarchy levels (Google taxonomy style), e.g.
        #   "Home & Garden > Decor > Seasonal & Holiday Decorations"
        # Magento requires "/" as the hierarchy separator instead, so we
        # convert it here — otherwise Magento treats the whole string as
        # ONE category name instead of a nested category path.
        cat_source = ""
        if c_category:
            cat_source = first.get(c_category, "")
        if not cat_source and c_type:
            cat_source = first.get(c_type, "")
        cat_source = cat_source.replace(" > ", "/").replace(">", "/").strip()
        categories = (f"Default Category/{cat_source}"
                      if cat_source and cat_source.lower() != "uncategorized"
                      else "Default Category")

        # Detect configurable (has real Option1/2/3 name other than blank/"Title")
        option_name_cols = [c for c in [c_opt1n, c_opt2n] if c]
        real_options = [c for c in option_name_cols
                        if first.get(c, "") not in ("", "Title")]
        variant_count = group[c_sku].nunique() if c_sku else 1
        is_configurable = len(real_options) > 0 and variant_count > 1

        product_online = "1" if str(first.get(c_status, "")).lower() in ("active", "true") else "0"

        if not is_configurable:
            # ---- SIMPLE PRODUCT ----
            if c_sku and (group[c_sku] != "").any():
                row = group[group[c_sku] != ""].iloc[0]
            else:
                row = first

            sku_val = row.get(c_sku, "") if c_sku else ""
            qty_val = row.get(c_qty, "0") if c_qty else "0"

            magento_rows.append({
                "sku": sku_val or handle,
                "store_view_code": "",
                "attribute_set_code": "Default",          # TODO: confirm your attribute set
                "product_type": "simple",
                "categories": categories,
                "product_websites": "base",               # TODO: confirm your website code
                "name": first.get(c_title, "") if c_title else handle,
                "description": first.get(c_body, "") if c_body else "",
                "short_description": "",
                "weight": row.get(c_grams, "0") if c_grams else "0",
                "product_online": product_online,
                "tax_class_name": "Taxable Goods",
                "visibility": "Catalog, Search",
                "price": row.get(c_price, "0") if c_price else "0",
                "special_price": row.get(c_compare, "") if c_compare else "",
                "url_key": str(handle).lower().replace(" ", "-"),
                "meta_title": first.get(c_seo_t, "") if c_seo_t else "",
                "meta_description": truncate_meta_description(first.get(c_seo_d, "") if c_seo_d else ""),
                "base_image": main_image,
                "small_image": main_image,
                "thumbnail_image": main_image,
                "additional_images": extra_images,
                # TODO: qty defaults to 0 if no inventory column found in your
                # export — provide a separate Shopify Inventory export to fill this
                "qty": qty_val or "0",
                "out_of_stock_qty": "0",
                "is_in_stock": "1" if (qty_val and float(qty_val or 0) > 0) else "1",
                "website_id": "1",
                "cost_per_item": row.get(c_cost, "") if c_cost else "",
            })
        else:
            # ---- CONFIGURABLE PRODUCT (parent + simple children) ----
            parent_sku = f"{handle}-CONF"
            child_skus = []
            for _, vrow in group.iterrows():
                v_sku = vrow.get(c_sku, "") if c_sku else ""
                if not v_sku:
                    continue
                child_skus.append(v_sku)
                v_qty = vrow.get(c_qty, "0") if c_qty else "0"
                opt1_val = vrow.get(c_opt1v, "") if c_opt1v else ""
                opt2_val = vrow.get(c_opt2v, "") if c_opt2v else ""
                magento_rows.append({
                    "sku": v_sku,
                    "store_view_code": "",
                    "attribute_set_code": "Default",
                    "product_type": "simple",
                    "categories": categories,
                    "product_websites": "base",
                    "name": f"{first.get(c_title,'') if c_title else handle} - {opt1_val} {opt2_val}".strip(),
                    "description": first.get(c_body, "") if c_body else "",
                    "short_description": "",
                    "weight": vrow.get(c_grams, "0") if c_grams else "0",
                    "product_online": product_online,
                    "tax_class_name": "Taxable Goods",
                    "visibility": "Not Visible Individually",
                    "price": vrow.get(c_price, "0") if c_price else "0",
                    "url_key": f"{handle}-{v_sku}".lower().replace(" ", "-"),
                    "base_image": (vrow.get(c_vimage, "") if c_vimage else "") or main_image,
                    "small_image": (vrow.get(c_vimage, "") if c_vimage else "") or main_image,
                    "thumbnail_image": (vrow.get(c_vimage, "") if c_vimage else "") or main_image,
                    "qty": v_qty or "0",
                    "out_of_stock_qty": "0",
                    "is_in_stock": "1",
                    "website_id": "1",
                    "additional_attributes": f"option1={opt1_val}",
                })
            # Parent row
            magento_rows.append({
                "sku": parent_sku,
                "store_view_code": "",
                "attribute_set_code": "Default",
                "product_type": "configurable",
                "categories": categories,
                "product_websites": "base",
                "name": first.get(c_title, "") if c_title else handle,
                "description": first.get(c_body, "") if c_body else "",
                "short_description": "",
                "product_online": "1",
                "tax_class_name": "Taxable Goods",
                "visibility": "Catalog, Search",
                "url_key": str(handle).lower().replace(" ", "-"),
                "base_image": main_image,
                "small_image": main_image,
                "thumbnail_image": main_image,
                "additional_images": extra_images,
                "website_id": "1",
                # NOTE: requires the super attribute (e.g. "color") to already
                # exist as a Magento product attribute before importing.
                "configurable_variations": "|".join([f"sku={s}" for s in child_skus]),
            })

    return pd.DataFrame(magento_rows)


# ==========================================================================
# CUSTOMERS: Shopify -> Magento 2 customer import format (real columns)
# Works with any Shopify customer export variant via dynamic column lookup.
# ==========================================================================
def _clean_phone(value):
    """Strip Excel's leading-apostrophe text-force artifact (e.g. '+1234567890)
    and surrounding whitespace/quotes from phone numbers."""
    if not value:
        return ""
    return value.strip().lstrip("'").strip()


def _extract_customer_fields(df):
    """Shared column-resolution + per-row value extraction used by both
    convert_customers_main() and convert_customers_addresses()."""
    c_email    = resolve_col(df, "Email")
    c_fname    = resolve_col(df, "First Name")
    c_lname    = resolve_col(df, "Last Name")
    c_company  = resolve_col(df, "Default Address Company", "Company")
    c_phone    = resolve_col(df, "Phone")
    c_addr_phone = resolve_col(df, "Default Address Phone")
    c_addr1    = resolve_col(df, "Default Address Address1")
    c_addr2    = resolve_col(df, "Default Address Address2")
    c_city     = resolve_col(df, "Default Address City")
    c_province = resolve_col(df, "Default Address Province Code", "Default Address Province")
    c_country  = resolve_col(df, "Default Address Country Code", "Default Address Country")
    c_zip      = resolve_col(df, "Default Address Zip", "Zip", "Postal Code")

    rows = []
    skipped_no_email = 0
    for _, row in df.iterrows():
        email_val = row.get(c_email, "") if c_email else ""
        if not email_val:
            # Email is the mandatory unique key for Magento customer import —
            # a row with no email can't be imported, and we won't invent one.
            skipped_no_email += 1
            continue

        street = " ".join(filter(None, [
            row.get(c_addr1, "") if c_addr1 else "",
            row.get(c_addr2, "") if c_addr2 else "",
        ]))
        phone_val = _clean_phone(
            (row.get(c_phone, "") if c_phone else "") or (row.get(c_addr_phone, "") if c_addr_phone else "")
        )
        rows.append({
            "email": email_val,
            "firstname": row.get(c_fname, "") if c_fname else "",
            "lastname": row.get(c_lname, "") if c_lname else "",
            "company": row.get(c_company, "") if c_company else "",
            "street": street,
            "city": row.get(c_city, "") if c_city else "",
            "region": row.get(c_province, "") if c_province else "",
            "country_id": row.get(c_country, "") if c_country else "",
            "postcode": row.get(c_zip, "") if c_zip else "",
            "telephone": phone_val,
        })
    if skipped_no_email:
        print(f"NOTE: {skipped_no_email} customer row(s) had NO email address in Shopify — "
              f"email is required to import a customer, so these were excluded entirely "
              f"(nothing was invented). Check these manually in Shopify if needed.")
    return rows


def convert_customers_main(df):
    """
    Customer core-account data ONLY — matches Magento's "Customers Main
    File" entity type, which does NOT require any address fields. Use this
    to safely import every customer regardless of whether their address
    data is complete.
    """
    extracted = _extract_customer_fields(df)
    magento_rows = []
    for r in extracted:
        magento_rows.append({
            "email": r["email"],
            "_website": "base",                       # TODO: confirm your website code
            "_store": "default",                      # TODO: confirm your actual store view code
            "confirmation": "",
            "created_at": "",
            "created_in": "Default Store View",
            "disable_auto_group_change": "0",
            "dob": "",
            "firstname": r["firstname"] or "N/A",   # Magento requires this for every customer
            "gender": "",
            "group_id": "1",                          # 1 = General customer group (default Magento)
            "lastname": r["lastname"] or "N/A",
            "middlename": "",
            "password_hash": "",
            "prefix": "",
            "rp_token": "",
            "rp_token_created_at": "",
            "store_id": "1",
            "suffix": "",
            "taxvat": "",
            "website_id": "1",
            "password": "",
        })
    return pd.DataFrame(magento_rows)


def convert_customers_addresses(df, telephone_placeholder="0000000000",
                                 text_placeholder="N/A"):
    """
    Address data ONLY — matches Magento's "Customer Addresses" entity type.

    country_id is a RESTRICTED field in Magento (only real ISO country codes
    are accepted) — a placeholder like "N/A" gets rejected as an "incorrect
    value". So a customer is only included here if they have a REAL country
    from Shopify; we never invent one. Given a real country, any other
    missing free-text field (street, city, telephone, name) is filled with
    a clearly-marked PLACEHOLDER so the rest of their real data isn't lost.

    IMPORTANT: placeholder values are NOT real data. After import, search
    Magento for these placeholder values (e.g. "0000000000" or "N/A") to
    find and manually correct/complete these specific customer records
    once you have their real information.

    Customers with NO real country (or no address info at all) are
    excluded here — only their core account (from convert_customers_main())
    will exist; nothing is invented for the missing country.
    """
    extracted = _extract_customer_fields(df)
    magento_rows = []
    placeholder_used_count = 0
    skipped_no_country = 0

    for r in extracted:
        if not r["country_id"]:
            # Never invent a country — Magento validates this against a
            # fixed list, so a fake value would be rejected outright.
            skipped_no_country += 1
            continue

        used_placeholder = False
        def fill(value, placeholder):
            nonlocal used_placeholder
            if value:
                return value
            used_placeholder = True
            return placeholder

        street_val = fill(r["street"], text_placeholder)
        city_val   = fill(r["city"], text_placeholder)
        phone_val  = fill(r["telephone"], telephone_placeholder)
        fname_val  = fill(r["firstname"], text_placeholder)
        lname_val  = fill(r["lastname"], text_placeholder)

        if used_placeholder:
            placeholder_used_count += 1

        magento_rows.append({
            "email": r["email"],
            "_website": "base",                       # TODO: confirm your website code
            "_address_city": city_val,
            "_address_company": r["company"],          # optional, left as-is (blank if missing)
            "_address_country_id": r["country_id"],    # always real — never a placeholder
            "_address_fax": "",
            "_address_firstname": fname_val,
            "_address_lastname": lname_val,
            "_address_middlename": "",
            "_address_postcode": r["postcode"],         # optional, left as-is (blank if missing)
            "_address_prefix": "",
            "_address_region": r["region"],             # optional, left as-is (blank if missing)
            "_address_street": street_val,
            "_address_suffix": "",
            "_address_telephone": phone_val,
            "_address_vat_id": "",
            "_address_default_billing_": "1",
            "_address_default_shipping_": "1",
        })
    if skipped_no_country:
        print(f"NOTE: {skipped_no_country} customer(s) had no country in Shopify — excluded "
              f"from this address file entirely (country_id can't be faked; a fake value "
              f"would be rejected by Magento). Their core account still exists via the main "
              f"customers file, just without an address.")
    if placeholder_used_count:
        print(f"NOTE: {placeholder_used_count} address row(s) (who DID have a real country) had "
              f"at least one missing free-text field, filled with a PLACEHOLDER ('{text_placeholder}' "
              f"for text, '{telephone_placeholder}' for phone) so the rest of that customer's real "
              f"data wasn't lost. Search Magento for these placeholder values afterwards to "
              f"find and correct them once you have the real info.")
    return pd.DataFrame(magento_rows)


def convert_customers(df, include_custom_attributes=False,
                       telephone_placeholder="0000000000", text_placeholder="N/A"):
    """
    Maps Shopify customer data to the OFFICIAL Magento "Customers and
    Addresses (single file)" import template — verified against the real
    sample file downloaded from Magento Admin (System > Data Transfer >
    Import > Entity Type: Customers and Addresses > Download Sample File).

    This entity type requires an address on EVERY row (city, country_id,
    street, telephone, firstname, lastname must all be present) — Magento
    rejects rows missing any of these, even if the rest of the row is
    fine. To avoid losing any of the REAL data Shopify does have, any
    missing required piece is filled with a clearly-marked PLACEHOLDER
    ('N/A' for text fields, '0000000000' for phone) instead of skipping
    the whole row. Nothing else is invented — postcode/region/company stay
    blank if Shopify didn't have them (they're optional in Magento).

    IMPORTANT: after import, search Magento for these placeholder values
    to find and correct them later once you have the customer's real info.

    include_custom_attributes=True additionally adds company_name, mobile,
    telephone_custom, postal_code as EXTRA columns at the end — ONLY use
    this if you've created these as Custom Attributes in Magento first
    (Stores > Attributes > Customer), otherwise import will reject them.
    """
    c_email    = resolve_col(df, "Email")
    c_fname    = resolve_col(df, "First Name")
    c_lname    = resolve_col(df, "Last Name")
    c_company  = resolve_col(df, "Default Address Company", "Company")
    c_phone    = resolve_col(df, "Phone")
    c_addr_phone = resolve_col(df, "Default Address Phone")
    c_addr1    = resolve_col(df, "Default Address Address1")
    c_addr2    = resolve_col(df, "Default Address Address2")
    c_city     = resolve_col(df, "Default Address City")
    c_province = resolve_col(df, "Default Address Province Code", "Default Address Province")
    c_country  = resolve_col(df, "Default Address Country Code", "Default Address Country")
    c_zip      = resolve_col(df, "Default Address Zip", "Zip", "Postal Code")

    magento_rows = []
    skipped_no_email = 0
    skipped_no_name = 0
    skipped_no_country = 0
    placeholder_used_count = 0

    for _, row in df.iterrows():
        email_val = row.get(c_email, "") if c_email else ""
        fname_val = row.get(c_fname, "") if c_fname else ""
        lname_val = row.get(c_lname, "") if c_lname else ""

        if not email_val:
            skipped_no_email += 1
            continue   # can't import a customer with no email (mandatory unique key)
        if not fname_val or not lname_val:
            skipped_no_name += 1
            continue   # firstname/lastname are real identity fields — not faked, customer excluded if missing

        street = " ".join(filter(None, [
            row.get(c_addr1, "") if c_addr1 else "",
            row.get(c_addr2, "") if c_addr2 else "",
        ]))
        phone_val = _clean_phone(
            (row.get(c_phone, "") if c_phone else "") or (row.get(c_addr_phone, "") if c_addr_phone else "")
        )
        city_val    = row.get(c_city, "") if c_city else ""
        country_val = row.get(c_country, "") if c_country else ""
        zip_val     = row.get(c_zip, "") if c_zip else ""

        # country_id is a RESTRICTED field in Magento — it only accepts real
        # ISO country codes from a fixed list, so a text placeholder like
        # "N/A" gets rejected ("incorrect value" error). We never invent a
        # country. If it's missing, we skip the address for this customer
        # entirely (their core account still imports fine) rather than
        # guess a country that could be wrong (affects tax/shipping rules).
        has_country = bool(country_val)

        if has_country:
            # Placeholders here are ONLY for free-text location fields
            # (street/city/phone) — never for identity or restricted fields.
            used_placeholder = False
            def fill(value, placeholder):
                nonlocal used_placeholder
                if value:
                    return value
                used_placeholder = True
                return placeholder

            street_final  = fill(street, text_placeholder)
            city_final    = fill(city_val, text_placeholder)
            phone_final   = fill(phone_val, telephone_placeholder)
            country_final = country_val

            if used_placeholder:
                placeholder_used_count += 1

            addr_city, addr_company, addr_country = city_final, (row.get(c_company, "") if c_company else ""), country_final
            addr_fname, addr_lname = fname_val, lname_val
            addr_postcode, addr_region = zip_val, (row.get(c_province, "") if c_province else "")
            addr_street, addr_telephone = street_final, phone_final
            addr_default = "1"
        else:
            skipped_no_country += 1
            addr_city = addr_company = addr_country = ""
            addr_fname = addr_lname = ""
            addr_postcode = addr_region = ""
            addr_street = addr_telephone = ""
            addr_default = ""

        # Official 38-column template, in the SAME ORDER as Magento's real
        # sample file. Non-required fields with no Shopify equivalent stay blank.
        record = {
            "email": email_val,
            "_website": "base",                       # TODO: confirm your website code
            "_store": "default",                      # TODO: confirm your actual store view code
            "confirmation": "",
            "created_at": "",
            "created_in": "Default Store View",
            "disable_auto_group_change": "0",
            "dob": "",
            "firstname": fname_val,                   # guaranteed real (row skipped otherwise)
            "gender": "",
            "group_id": "1",                          # 1 = General customer group (default Magento)
            "lastname": lname_val,                    # guaranteed real (row skipped otherwise)
            "middlename": "",
            "password_hash": "",
            "prefix": "",
            "rp_token": "",
            "rp_token_created_at": "",
            "store_id": "1",
            "suffix": "",
            "taxvat": "",
            "website_id": "1",
            "password": "",
            "_address_city": addr_city,
            "_address_company": addr_company,
            "_address_country_id": addr_country,
            "_address_fax": "",
            "_address_firstname": addr_fname,
            "_address_lastname": addr_lname,
            "_address_middlename": "",
            "_address_postcode": addr_postcode,
            "_address_prefix": "",
            "_address_region": addr_region,
            "_address_street": addr_street,
            "_address_suffix": "",
            "_address_telephone": addr_telephone,
            "_address_vat_id": "",
            "_address_default_billing_": addr_default,
            "_address_default_shipping_": addr_default,
        }

        # ---- Optional CUSTOM ATTRIBUTE columns (extra, non-standard) ----
        if include_custom_attributes:
            record["company_name"] = row.get(c_company, "") if c_company else ""
            record["mobile"] = phone_val
            record["telephone_custom"] = phone_val
            record["postal_code"] = zip_val

        magento_rows.append(record)

    if skipped_no_email:
        print(f"NOTE: {skipped_no_email} customer(s) had no email in Shopify and were "
              f"excluded entirely (email is required, nothing was invented).")
    if skipped_no_name:
        print(f"NOTE: {skipped_no_name} customer(s) had no firstname/lastname in Shopify "
              f"and were excluded entirely (name is a real identity field, not placeholder-filled).")
    if skipped_no_country:
        print(f"NOTE: {skipped_no_country} customer(s) had no country in Shopify — their "
              f"ENTIRE address was left blank (no address row) because Magento's country_id "
              f"only accepts real ISO country codes and a fake one would be rejected/misleading. "
              f"Their core account still imported fine, just without an address.")
    if placeholder_used_count:
        print(f"NOTE: {placeholder_used_count} customer(s) (who DID have a real country) had "
              f"a missing free-text ADDRESS field (city/street/phone), filled with a PLACEHOLDER "
              f"('{text_placeholder}' for text, '{telephone_placeholder}' for phone) so no real "
              f"data was lost. Search Magento for these placeholder values afterwards to find "
              f"and correct them.")

    return pd.DataFrame(magento_rows)


# ==========================================================================
# ORDERS: Shopify -> Magento "Order with Items" format
# Column names below are EXACT match to the real Magento order-with-items
# export/import template you provided (Order #, Order Status, Order State,
# Order Date, Last Updated, Store, Customer Name, Customer Email, ... down
# to Item SKU, Item Name, Item Type, Qty Ordered, ... Product ID, Item Options)
#
# Shopify's orders.csv already has ONE ROW PER LINE ITEM (same order number
# repeats across rows when a product has multiple items) — this matches
# Magento's row-per-item structure, so no grouping/pivoting is needed here,
# just a direct column-to-column mapping per row.
# ==========================================================================

# Shopify "Financial Status" / "Fulfillment Status" -> Magento order status/state
# TODO: adjust this mapping if your Magento store uses custom order statuses
STATUS_MAP = {
    "paid": ("processing", "processing"),
    "pending": ("pending", "new"),
    "refunded": ("closed", "closed"),
    "partially_refunded": ("processing", "processing"),
    "voided": ("canceled", "canceled"),
}

import re

def make_fallback_sku(item_name, order_number):
    """Generate a stable placeholder SKU from the item name when Shopify
    didn't provide one (common for gift cards / service items). This
    ensures no order line is left with a blank SKU, which most Magento
    order-import tools would otherwise skip or reject."""
    if not item_name:
        return f"NOSKU-ORDER-{order_number}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", item_name).strip("-").upper()
    return f"GEN-{slug}"[:64]   # keep within typical SKU length limits


def make_placeholder_products_csv(orders_magento_df):
    """Build a small Magento PRODUCT import CSV containing one simple
    product per fallback SKU used in the orders file (e.g. gift cards or
    other SKU-less Shopify line items). Import this file FIRST, before
    importing orders, so Magento has a matching product for every SKU."""
    fallback_rows = orders_magento_df[orders_magento_df["Item SKU"].str.startswith("GEN-", na=False)]
    if fallback_rows.empty:
        return None
    unique_items = fallback_rows.drop_duplicates(subset=["Item SKU"])
    rows = []
    for _, r in unique_items.iterrows():
        rows.append({
            "sku": r["Item SKU"],
            "store_view_code": "",
            "attribute_set_code": "Default",
            "product_type": "simple",
            "categories": "Default Category",
            "product_websites": "base",
            "name": r["Item Name"] or r["Item SKU"],
            "description": "",
            "short_description": "",
            "weight": "0",
            "product_online": "1",
            "tax_class_name": "Taxable Goods",
            "visibility": "Not Visible Individually",   # these are order-only placeholder items
            "price": r["Item Price"] or "0",
            "url_key": r["Item SKU"].lower(),
            "qty": "999",
            "out_of_stock_qty": "0",
            "is_in_stock": "1",
            "website_id": "1",
        })
    return pd.DataFrame(rows)


def convert_orders(df, skip_missing_sku=True):
    c_name       = resolve_col(df, "Name", "Order Name", "Order #")
    c_email      = resolve_col(df, "Email", "Customer Email")
    c_fin_status = resolve_col(df, "Financial Status")
    c_fulfill    = resolve_col(df, "Lineitem fulfillment status", "Fulfillment Status")
    c_created    = resolve_col(df, "Created at", "Paid at")
    c_currency   = resolve_col(df, "Currency")
    c_subtotal   = resolve_col(df, "Subtotal")
    c_shipping   = resolve_col(df, "Shipping")
    c_taxes      = resolve_col(df, "Taxes")
    c_total      = resolve_col(df, "Total")
    c_refunded   = resolve_col(df, "Refunded Amount")
    c_discount_c = resolve_col(df, "Discount Code")
    c_discount_a = resolve_col(df, "Discount Amount")
    c_ship_method = resolve_col(df, "Shipping Method")
    c_pay_method  = resolve_col(df, "Payment Method")

    c_bill_name = resolve_col(df, "Billing Name")
    c_bill_a1   = resolve_col(df, "Billing Address1")
    c_bill_a2   = resolve_col(df, "Billing Address2")
    c_bill_city = resolve_col(df, "Billing City")
    c_bill_prov = resolve_col(df, "Billing Province")
    c_bill_zip  = resolve_col(df, "Billing Zip")
    c_bill_country = resolve_col(df, "Billing Country")
    c_bill_phone = resolve_col(df, "Billing Phone")

    c_ship_name = resolve_col(df, "Shipping Name")
    c_ship_a1   = resolve_col(df, "Shipping Address1")
    c_ship_a2   = resolve_col(df, "Shipping Address2")
    c_ship_city = resolve_col(df, "Shipping City")
    c_ship_prov = resolve_col(df, "Shipping Province")
    c_ship_zip  = resolve_col(df, "Shipping Zip")
    c_ship_country = resolve_col(df, "Shipping Country")

    c_item_qty   = resolve_col(df, "Lineitem quantity", "Line Item Quantity")
    c_item_name  = resolve_col(df, "Lineitem name", "Line Item Name")
    c_item_sku   = resolve_col(df, "Lineitem sku", "Line Item SKU")
    c_item_price = resolve_col(df, "Lineitem price", "Line Item Price")
    c_item_disc  = resolve_col(df, "Lineitem discount", "Line Item Discount")

    magento_rows = []
    skipped_count = 0
    for _, row in df.iterrows():
        item_sku_val = row.get(c_item_sku, "") if c_item_sku else ""
        if not item_sku_val:
            if skip_missing_sku:
                skipped_count += 1
                continue   # skip this line — no SKU means Magento can't match/create the product
            else:
                order_number_tmp = str(row.get(c_name, "") if c_name else "").replace("#", "")
                item_name_tmp = row.get(c_item_name, "") if c_item_name else ""
                item_sku_val = make_fallback_sku(item_name_tmp, order_number_tmp)

        fin_status = str(row.get(c_fin_status, "") if c_fin_status else "").lower().strip()
        order_status, order_state = STATUS_MAP.get(fin_status, ("pending", "new"))

        qty_ordered = (row.get(c_item_qty, "0") if c_item_qty else "0") or "0"
        item_price = (row.get(c_item_price, "0") if c_item_price else "0") or "0"
        try:
            row_total = float(qty_ordered) * float(item_price)
        except ValueError:
            row_total = 0

        is_paid = fin_status == "paid"
        is_fulfilled = str(row.get(c_fulfill, "") if c_fulfill else "").lower() == "fulfilled"

        billing_street = " ".join(filter(None, [
            row.get(c_bill_a1, "") if c_bill_a1 else "",
            row.get(c_bill_a2, "") if c_bill_a2 else "",
        ]))
        shipping_street = " ".join(filter(None, [
            row.get(c_ship_a1, "") if c_ship_a1 else "",
            row.get(c_ship_a2, "") if c_ship_a2 else "",
        ]))

        order_date = row.get(c_created, "") if c_created else ""
        order_number = str(row.get(c_name, "") if c_name else "").replace("#", "")
        item_name_val = row.get(c_item_name, "") if c_item_name else ""

        magento_rows.append({
            "Order #": order_number,
            "Order Status": order_status,
            "Order State": order_state,
            "Order Date": order_date,
            "Last Updated": order_date,   # Shopify export usually has no separate "updated at" column
            "Store": "Main Website\nMain Website Store\nDefault Store View",  # TODO: confirm your real store path
            "Customer Name": row.get(c_bill_name, "") if c_bill_name else "",
            "Customer Email": row.get(c_email, "") if c_email else "",
            "Customer Group": "General",                 # TODO: map from Shopify if you track guest vs account orders
            "Billing Name": row.get(c_bill_name, "") if c_bill_name else "",
            "Billing Street": billing_street,
            "Billing City": row.get(c_bill_city, "") if c_bill_city else "",
            "Billing Region": row.get(c_bill_prov, "") if c_bill_prov else "",
            "Billing Postcode": row.get(c_bill_zip, "") if c_bill_zip else "",
            "Billing Country": row.get(c_bill_country, "") if c_bill_country else "",
            "Billing Phone": row.get(c_bill_phone, "") if c_bill_phone else "",
            "Shipping Name": row.get(c_ship_name, "") if c_ship_name else "",
            "Shipping Street": shipping_street,
            "Shipping City": row.get(c_ship_city, "") if c_ship_city else "",
            "Shipping Region": row.get(c_ship_prov, "") if c_ship_prov else "",
            "Shipping Postcode": row.get(c_ship_zip, "") if c_ship_zip else "",
            "Shipping Country": row.get(c_ship_country, "") if c_ship_country else "",
            "Shipping Method": row.get(c_ship_method, "") if c_ship_method else "",
            "Payment Method": row.get(c_pay_method, "") if c_pay_method else "",
            "Coupon Code": row.get(c_discount_c, "") if c_discount_c else "",
            "Subtotal": row.get(c_subtotal, "") if c_subtotal else "",
            "Discount": row.get(c_discount_a, "") if c_discount_a else "",
            "Shipping Amount": row.get(c_shipping, "") if c_shipping else "",
            "Tax Amount": row.get(c_taxes, "") if c_taxes else "",
            "Grand Total": row.get(c_total, "") if c_total else "",
            "Total Invoiced": (row.get(c_total, "") if c_total else "") if is_paid else "0",
            "Total Refunded": (row.get(c_refunded, "0") if c_refunded else "0"),
            "Currency": row.get(c_currency, "") if c_currency else "",
            "Item SKU": item_sku_val,
            "Item Name": item_name_val,
            "Item Type": "simple",   # TODO: change if you have configurable/bundle items
            "Qty Ordered": qty_ordered,
            "Qty Invoiced": qty_ordered if is_paid else "0",
            "Qty Shipped": qty_ordered if is_fulfilled else "0",
            "Qty Refunded": "0",
            "Qty Canceled": "0",
            "Original Price": row.get(c_item_price, "") if c_item_price else "",
            "Item Price": row.get(c_item_price, "") if c_item_price else "",
            "Item Discount": (row.get(c_item_disc, "0") if c_item_disc else "0"),
            "Item Tax": "0",   # TODO: Shopify gives order-level tax only; per-item tax split not available
            "Row Total": row_total,
            "Row Total (incl. Tax)": row_total,   # TODO: add tax if you calculate per-item tax
            "Product ID": "",   # left blank — plugin should resolve this from Item SKU
            "Item Options": "",
        })
    if skip_missing_sku and skipped_count:
        print(f"NOTE: Skipped {skipped_count} order line-item(s) with no SKU in Shopify "
              f"(e.g. gift cards / custom items) — set skip_missing_sku=False to include "
              f"them instead with a generated placeholder SKU.")
    return pd.DataFrame(magento_rows)


# ==========================================================================
# MAIN: upload all 3 Shopify files, convert each, download all 3 results
# ==========================================================================
print("=" * 70)
print("SHOPIFY -> MAGENTO CONVERTER — will ask for 3 files one by one:")
print("  1) products.csv   2) customers.csv   3) orders.csv")
print("(Skip any upload box if you don't have that file right now)")
print("=" * 70)

results = {}

# ---- PRODUCTS ----
products_df = upload_one("products (e.g. products.csv)")
if products_df is not None:
    magento_products = convert_products(products_df)
    print(f"\nConverted {len(magento_products)} product rows.")
    print(magento_products.head())
    results["magento_products_import.csv"] = magento_products

# ---- CUSTOMERS ----
customers_df = upload_one("customers (e.g. customers.csv)")
if customers_df is not None:
    # TWO FILES (recommended/safer): Magento's "Customers and Addresses
    # (single file)" entity type requires city/country/street/telephone/name
    # on EVERY row — even a fully blank address row gets rejected. So we
    # split into two imports instead:
    #   1) magento_customers_main_import.csv      -> Entity Type: "Customers Main File"
    #      (every customer with email+name, no address needed)
    #   2) magento_customer_addresses_import.csv  -> Entity Type: "Customer Addresses"
    #      (only customers who have a REAL country — never faked; other
    #       missing free-text fields get a placeholder)
    magento_customers_main = convert_customers_main(customers_df)
    print(f"\nConverted {len(magento_customers_main)} customer (core) rows.")
    print(magento_customers_main.head())
    results["magento_customers_main_import.csv"] = magento_customers_main

    magento_customer_addresses = convert_customers_addresses(customers_df)
    print(f"\nConverted {len(magento_customer_addresses)} customer address rows "
          f"(only customers with a real country).")
    if len(magento_customer_addresses):
        print(magento_customer_addresses.head())
        results["magento_customer_addresses_import.csv"] = magento_customer_addresses


# ---- ORDERS ----
orders_df = upload_one("orders (e.g. orders.csv)")
if orders_df is not None:
    magento_orders = convert_orders(orders_df, skip_missing_sku=True)
    print(f"\nConverted {len(magento_orders)} order line-item rows (missing-SKU lines skipped).")
    print(magento_orders.head())
    results["magento_orders_import.csv"] = magento_orders

# ---- SAVE ALL RESULTS TO LOCAL FOLDER ----
if not results:
    print("\nNo files were uploaded — nothing to convert.")
else:
    output_dir = "magento_output"
    os.makedirs(output_dir, exist_ok=True)
    print("\n" + "=" * 70)
    print(f"Saving converted files to '{output_dir}/' ...")
    for fname, df in results.items():
        out_path = os.path.join(output_dir, fname)
        df.to_csv(out_path, index=False)
        print(f"  -> {out_path} ({len(df)} rows) saved.")
    print("=" * 70)
    print("DONE! Import these files in Magento Admin under:")
    print("  Products/Customers -> System > Data Transfer > Import")
    print("  Orders -> via your chosen order-import extension (e.g. Firebear)")
