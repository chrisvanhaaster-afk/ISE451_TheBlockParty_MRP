import streamlit as st
import pandas as pd
from collections import defaultdict
from urllib.parse import quote

# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(
    page_title="The Block Party MRP",
    page_icon="🧱",
    layout="wide"
)

# =========================================================
# GOOGLE SHEET
# =========================================================

SHEET_ID = "1NIS7PrX1yZXGK-0i3bpRQZ_q4xv0eNz5NOHpLfG7kcE"


# =========================================================
# GOOGLE SHEET LOADERS
# =========================================================

def load_sheet(sheet_name):

    encoded_name = quote(sheet_name)

    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv"
        f"&sheet={encoded_name}"
    )

    return pd.read_csv(
        url,
        header=None
    )


def load_sheet_range(sheet_name, cell_range):

    encoded_name = quote(sheet_name)
    encoded_range = quote(cell_range)

    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv"
        f"&sheet={encoded_name}"
        f"&range={encoded_range}"
    )

    return pd.read_csv(
        url,
        header=None
    )


# =========================================================
# LOAD DATA
# =========================================================

try:

    # IMPORTANT:
    # Production Plan begins at column D.
    # Loading a defined range prevents blank columns
    # from shifting our positions.

    production_sheet = load_sheet_range(
        "Production Plan",
        "D1:AZ20"
    )

    bom_sheet = load_sheet("BOM")

    inventory_sheet = load_sheet("Inventory")

except Exception as e:

    st.error("Could not read the Google Sheet.")

    st.code(str(e))

    st.stop()


# =========================================================
# HELPERS
# =========================================================

def get_value(df, row, col):

    try:

        value = df.iloc[row, col]

        if pd.isna(value):
            return None

        return value

    except:
        return None


def clean_number(value):

    try:

        if value is None:
            return 0

        return int(float(value))

    except:
        return 0


def find_text(df, text):

    target = str(text).strip().upper()

    matches = []

    for row in range(len(df)):

        for col in range(len(df.columns)):

            value = get_value(
                df,
                row,
                col
            )

            if value is None:
                continue

            if str(value).strip().upper() == target:

                matches.append(
                    (row, col)
                )

    return matches


# =========================================================
# BILL OF MATERIALS
# =========================================================

def find_bom(product_name):

    target = f"{product_name.upper()} BOM"

    matches = find_text(
        bom_sheet,
        target
    )

    if not matches:
        return {}

    # Use LAST occurrence so we get your bottom BOM
    title_row, title_col = matches[-1]

    part_col = title_col
    qty_col = title_col + 1

    data_row = title_row + 2

    bom = {}

    while data_row < len(bom_sheet):

        part = get_value(
            bom_sheet,
            data_row,
            part_col
        )

        qty = get_value(
            bom_sheet,
            data_row,
            qty_col
        )

        if part is None:
            break

        part_text = str(part).strip()

        if "TOTAL" in part_text.upper():
            break

        quantity = clean_number(qty)

        if quantity > 0:

            bom[part_text] = quantity

        data_row += 1

    return bom


BOMS = {
    "Stair": find_bom("Stair"),
    "Star": find_bom("Star"),
    "Box": find_bom("Box"),
    "Cube": find_bom("Cube")
}


# =========================================================
# WEEK SETUP
# =========================================================

WEEKS = [
    f"Week {i}"
    for i in range(1, 10)
]


# =========================================================
# PRODUCTION PLAN
# =========================================================

def read_production_plan(week_number):

    production = {
        "Stair": 0,
        "Star": 0,
        "Box": 0,
        "Cube": 0
    }

    # -----------------------------------------------------
    # Because we loaded starting at spreadsheet column D:
    #
    # pandas 0 = D = Product
    #
    # Week 1:
    # E = FD  -> pandas 1
    # F = AD  -> pandas 2
    # G = TB  -> pandas 3
    # H = AS  -> pandas 4
    #
    # Week 2:
    # J = FD  -> pandas 6
    # K = AD  -> pandas 7
    # L = TB  -> pandas 8
    # M = AS  -> pandas 9
    #
    # Therefore each week's TB moves exactly 5 columns.
    # -----------------------------------------------------

    target_build_col = (
        3
        + ((week_number - 1) * 5)
    )

    # -----------------------------------------------------
    # Find product names dynamically in column D.
    # -----------------------------------------------------

    for row in range(len(production_sheet)):

        product_value = get_value(
            production_sheet,
            row,
            0
        )

        if product_value is None:
            continue

        product_name = str(
            product_value
        ).strip()

        for product in production:

            if product_name.upper() == product.upper():

                target_build = get_value(
                    production_sheet,
                    row,
                    target_build_col
                )

                production[product] = clean_number(
                    target_build
                )

    return production


# =========================================================
# INVENTORY
# =========================================================

def read_inventory(week_number):

    inventory = {}

    # Current inventory mapping:
    #
    # Week 1 Carryover = C
    # Each week advances 8 columns.
    #
    # We can make this dynamic after confirming
    # the Inventory sheet structure.

    carryover_col = (
        2
        + ((week_number - 1) * 8)
    )

    for row in range(len(inventory_sheet)):

        part = get_value(
            inventory_sheet,
            row,
            1
        )

        if part is None:
            continue

        part = str(part).strip()

        if part.upper() in [
            "PN",
            "PART NUMBER"
        ]:
            continue

        rollover = get_value(
            inventory_sheet,
            row,
            carryover_col
        )

        inventory[part] = clean_number(
            rollover
        )

    return inventory


# =========================================================
# MRP CALCULATION
# =========================================================

def calculate_mrp(
    production_plan,
    inventory
):

    gross_requirements = defaultdict(int)

    # -----------------------------------------------------
    # BOM EXPLOSION
    # -----------------------------------------------------

    for product, build_qty in production_plan.items():

        if build_qty <= 0:
            continue

        for part, qty_per_product in BOMS.get(
            product,
            {}
        ).items():

            gross_requirements[part] += (
                build_qty
                * qty_per_product
            )

    # -----------------------------------------------------
    # NET REQUIREMENTS
    # -----------------------------------------------------

    results = []

    for part, gross_required in sorted(
        gross_requirements.items()
    ):

        rollover = inventory.get(
            part,
            0
        )

        qty_to_purchase = max(
            gross_required - rollover,
            0
        )

        projected_remaining = max(
            rollover - gross_required,
            0
        )

        results.append({
            "Part Number": part,
            "Gross Requirement": gross_required,
            "Rollover Inventory": rollover,
            "Qty to Purchase": qty_to_purchase,
            "Projected Remaining": projected_remaining
        })

    return results


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title(
    "🧱 The Block Party"
)

st.sidebar.caption(
    "Material Requirements Planning"
)

selected_week = st.sidebar.selectbox(
    "Production Week",
    WEEKS
)

week_number = int(
    selected_week.replace(
        "Week ",
        ""
    )
)

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Production Plan",
        "Inventory",
        "Bill of Materials",
        "Purchasing"
    ]
)

st.sidebar.divider()

if st.sidebar.button(
    "🔄 Refresh Google Sheet"
):

    st.rerun()


# =========================================================
# CURRENT DATA
# =========================================================

production_plan = read_production_plan(
    week_number
)

inventory = read_inventory(
    week_number
)

mrp_results = calculate_mrp(
    production_plan,
    inventory
)


# =========================================================
# DASHBOARD
# =========================================================

if page == "Dashboard":

    st.title(
        "🧱 The Block Party MRP"
    )

    st.caption(
        f"{selected_week} Manufacturing Overview"
    )

    st.success(
        "Connected to live Google Sheet"
    )

    total_products = sum(
        production_plan.values()
    )

    total_parts = sum(
        row["Gross Requirement"]
        for row in mrp_results
    )

    total_purchase = sum(
        row["Qty to Purchase"]
        for row in mrp_results
    )

    shortage_pns = sum(
        1
        for row in mrp_results
        if row["Qty to Purchase"] > 0
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Products Planned",
        total_products
    )

    col2.metric(
        "Parts Required",
        total_parts
    )

    col3.metric(
        "Parts to Purchase",
        total_purchase
    )

    col4.metric(
        "PNs With Shortages",
        shortage_pns
    )

    st.divider()

    # -----------------------------------------------------
    # TARGET BUILD
    # -----------------------------------------------------

    st.subheader(
        "Target Build"
    )

    target_data = [
        {
            "Product": product,
            "Target Build": quantity
        }
        for product, quantity
        in production_plan.items()
    ]

    st.dataframe(
        target_data,
        use_container_width=True,
        hide_index=True
    )

    # -----------------------------------------------------
    # MRP SUMMARY
    # -----------------------------------------------------

    st.subheader(
        "MRP Summary"
    )

    if mrp_results:

        st.dataframe(
            mrp_results,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No material requirements "
            f"for {selected_week}."
        )


# =========================================================
# PRODUCTION PLAN
# =========================================================

elif page == "Production Plan":

    st.title(
        "Production Plan"
    )

    st.caption(
        f"Live Google Sheet — {selected_week}"
    )

    st.info(
        "Target Build values are pulled directly "
        "from the TB column in the shared "
        "Production Plan sheet."
    )

    production_data = [
        {
            "Product": product,
            "Target Build": quantity
        }
        for product, quantity
        in production_plan.items()
    ]

    st.dataframe(
        production_data,
        use_container_width=True,
        hide_index=True
    )

    st.metric(
        "Total Products Planned",
        sum(
            production_plan.values()
        )
    )

    st.divider()

    st.subheader(
        "Gross Material Requirements"
    )

    gross_data = [
        {
            "Part Number":
                row["Part Number"],

            "Required Quantity":
                row["Gross Requirement"]
        }
        for row in mrp_results
    ]

    if gross_data:

        st.dataframe(
            gross_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No material requirements "
            f"for {selected_week}."
        )


# =========================================================
# INVENTORY
# =========================================================

elif page == "Inventory":

    st.title(
        "Inventory"
    )

    st.caption(
        f"Live Google Sheet — {selected_week}"
    )

    st.write(
        "Inventory available for the current "
        "MRP calculation."
    )

    inventory_data = [
        {
            "Part Number": part,
            "Rollover Inventory": quantity
        }
        for part, quantity
        in sorted(inventory.items())
    ]

    if inventory_data:

        st.dataframe(
            inventory_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No inventory data found."
        )


# =========================================================
# BILL OF MATERIALS
# =========================================================

elif page == "Bill of Materials":

    st.title(
        "Bill of Materials"
    )

    st.caption(
        "Bottom BOMs from the live Google Sheet"
    )

    selected_product = st.selectbox(
        "Product",
        [
            "Stair",
            "Star",
            "Box",
            "Cube"
        ]
    )

    selected_bom = BOMS.get(
        selected_product,
        {}
    )

    bom_data = [
        {
            "Part Number": part,
            "Quantity per Product": quantity
        }
        for part, quantity
        in selected_bom.items()
    ]

    if bom_data:

        st.dataframe(
            bom_data,
            use_container_width=True,
            hide_index=True
        )

        st.metric(
            "Unique Part Numbers",
            len(bom_data)
        )

    else:

        st.warning(
            f"No BOM information found "
            f"for {selected_product}."
        )


# =========================================================
# PURCHASING
# =========================================================

elif page == "Purchasing":

    st.title(
        "Purchasing Requirements"
    )

    st.caption(
        f"Independent MRP — {selected_week}"
    )

    st.write(
        "Calculated from Target Build × BOM, "
        "then adjusted for rollover inventory."
    )

    purchase_data = [
        {
            "Part Number":
                row["Part Number"],

            "Gross Requirement":
                row["Gross Requirement"],

            "Rollover Inventory":
                row["Rollover Inventory"],

            "Qty to Purchase":
                row["Qty to Purchase"]
        }

        for row in mrp_results

        if row["Qty to Purchase"] > 0
    ]

    if purchase_data:

        st.dataframe(
            purchase_data,
            use_container_width=True,
            hide_index=True
        )

        st.metric(
            "Total Pieces to Purchase",
            sum(
                row["Qty to Purchase"]
                for row in purchase_data
            )
        )

    else:

        st.success(
            "No parts need to be purchased "
            f"for {selected_week}."
        )