
import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import hashlib
import secrets
import re
from pathlib import Path

# =====================================================
# POWERMATE - SMART HOME ELECTRICITY SYSTEM
# =====================================================

st.set_page_config(
    page_title="POWERMATE",
    page_icon="⚡",
    layout="wide"
)

DB_FILE = Path(__file__).with_name("powermate.db")

DEFAULT_SETTINGS = {
    "rate1": 3.0,
    "rate2": 5.0,
    "rate3": 7.0,
    "rate4": 8.0,
    "fixed": 100.0,
    "extra": 0.0,
    "tax": 5.0
}


# =====================================================
# DATABASE
# =====================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database():
    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS appliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                wattage REAL NOT NULL,
                quantity INTEGER NOT NULL,
                hours REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        # Migrate an older POWERMATE database if necessary.
        columns = [
            row[1] for row in conn.execute(
                "PRAGMA table_info(appliances)"
            ).fetchall()
        ]

        if "user_id" not in columns:
            conn.execute(
                "ALTER TABLE appliances ADD COLUMN user_id INTEGER"
            )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL,
                setting TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY(user_id, setting),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)


setup_database()


# =====================================================
# PASSWORD SECURITY
# =====================================================

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        300000
    ).hex()


def register_user(username, phone, password):
    username = username.strip()
    phone = phone.strip()

    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        return False, (
            "Username must be 3-20 characters and contain "
            "only letters, numbers or underscores."
        )

    if not re.fullmatch(r"[0-9]{10}", phone):
        return False, "Enter a valid 10-digit phone number."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    salt = secrets.token_bytes(16).hex()
    password_hash = hash_password(password, salt)

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO users
                (username, phone, password_hash, salt)
                VALUES (?, ?, ?, ?)
            """, (username, phone, password_hash, salt))

        return True, "Account created successfully!"

    except sqlite3.IntegrityError:
        return False, "Username or phone number is already registered."


def authenticate_user(login_id, password):
    login_id = login_id.strip()

    with get_connection() as conn:
        user = conn.execute("""
            SELECT id, username, password_hash, salt
            FROM users
            WHERE username = ? COLLATE NOCASE OR phone = ?
        """, (login_id, login_id)).fetchone()

    if not user:
        return None

    user_id, username, stored_hash, salt = user
    entered_hash = hash_password(password, salt)

    if secrets.compare_digest(entered_hash, stored_hash):
        return {"id": user_id, "username": username}

    return None


# =====================================================
# USER SETTINGS
# =====================================================

def load_settings(user_id):
    settings = DEFAULT_SETTINGS.copy()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT setting, value
            FROM user_settings
            WHERE user_id = ?
        """, (user_id,)).fetchall()

    for key, value in rows:
        if key in settings:
            settings[key] = value

    return settings


def save_settings(user_id, settings):
    with get_connection() as conn:
        for key, value in settings.items():
            conn.execute("""
                INSERT INTO user_settings (user_id, setting, value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, setting)
                DO UPDATE SET value = excluded.value
            """, (user_id, key, value))


# =====================================================
# APPLIANCE DATABASE FUNCTIONS
# =====================================================

def load_appliances(user_id):
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT id, name, wattage, quantity, hours
            FROM appliances
            WHERE user_id = ?
            ORDER BY id
        """, conn, params=(user_id,))


def add_appliance(user_id, name, wattage, quantity, hours):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO appliances
            (user_id, name, wattage, quantity, hours)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, wattage, quantity, hours))


def update_appliance(
    user_id, appliance_id, name, wattage, quantity, hours
):
    with get_connection() as conn:
        conn.execute("""
            UPDATE appliances
            SET name = ?, wattage = ?, quantity = ?, hours = ?
            WHERE id = ? AND user_id = ?
        """, (
            name, wattage, quantity, hours,
            appliance_id, user_id
        ))


def delete_appliance(user_id, appliance_id):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM appliances
            WHERE id = ? AND user_id = ?
        """, (appliance_id, user_id))


# =====================================================
# DESIGN
# =====================================================

st.markdown("""
<style>
.stApp {
    background-color: #0b1220;
    color: white;
}
h1, h2, h3 {
    color: #38bdf8 !important;
}
div[data-testid="stMetric"] {
    background: #17243a;
    padding: 18px;
    border-radius: 12px;
    border: 1px solid #263b57;
}
section[data-testid="stSidebar"] {
    background: #101c30;
}
</style>
""", unsafe_allow_html=True)


# =====================================================
# LOGIN AND REGISTRATION
# =====================================================

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:

    st.title("⚡ POWERMATE")
    st.subheader("Smart Home Electricity Consumption & Billing System")
    st.write("Welcome! Login or create an account to manage your home electricity.")

    login_tab, register_tab = st.tabs([
        "🔐 Login",
        "📝 Create Account"
    ])

    with login_tab:

        st.header("Welcome Back")

        with st.form("login_form"):

            login_id = st.text_input(
                "Username or Phone Number",
                placeholder="Enter username or 10-digit phone number"
            )

            login_password = st.text_input(
                "Password",
                type="password"
            )

            login_button = st.form_submit_button(
                "Login",
                use_container_width=True
            )

            if login_button:

                user = authenticate_user(login_id, login_password)

                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Incorrect username/phone number or password.")

    with register_tab:

        st.header("Create Your POWERMATE Account")

        with st.form("register_form"):

            new_username = st.text_input(
                "Choose Username",
                placeholder="Example: poweruser01"
            )

            new_phone = st.text_input(
                "Phone Number",
                placeholder="Enter 10-digit phone number"
            )

            new_password = st.text_input(
                "Create Password",
                type="password"
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password"
            )

            register_button = st.form_submit_button(
                "Create Account",
                use_container_width=True
            )

            if register_button:

                if new_password != confirm_password:
                    st.error("Passwords do not match.")

                else:
                    success, message = register_user(
                        new_username,
                        new_phone,
                        new_password
                    )

                    if success:
                        st.success(
                            "Account created! Now go to the Login tab."
                        )
                    else:
                        st.error(message)

    st.stop()


# =====================================================
# AUTHENTICATED USER
# =====================================================

user_id = st.session_state.user["id"]
username = st.session_state.user["username"]

st.sidebar.title("⚡ POWERMATE")
st.sidebar.success(f"Logged in as {username}")

if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()


# =====================================================
# LOAD USER TARIFF SETTINGS
# =====================================================

settings = load_settings(user_id)

st.sidebar.divider()
st.sidebar.header("⚙️ Your Electricity Tariff")

with st.sidebar.form("tariff_form"):

    rate1 = st.number_input(
        "First 100 Units (₹/unit)",
        min_value=0.0,
        value=float(settings["rate1"])
    )

    rate2 = st.number_input(
        "Next 100 Units (₹/unit)",
        min_value=0.0,
        value=float(settings["rate2"])
    )

    rate3 = st.number_input(
        "Next 200 Units (₹/unit)",
        min_value=0.0,
        value=float(settings["rate3"])
    )

    rate4 = st.number_input(
        "Above 400 Units (₹/unit)",
        min_value=0.0,
        value=float(settings["rate4"])
    )

    fixed_charge = st.number_input(
        "Monthly Fixed Charges (₹)",
        min_value=0.0,
        value=float(settings["fixed"])
    )

    extra_charge = st.number_input(
        "Other Monthly Charges (₹)",
        min_value=0.0,
        value=float(settings["extra"])
    )

    tax_rate = st.number_input(
        "Tax (%)",
        min_value=0.0,
        value=float(settings["tax"])
    )

    save_tariff = st.form_submit_button("💾 Save My Tariff")

    if save_tariff:
        save_settings(user_id, {
            "rate1": rate1,
            "rate2": rate2,
            "rate3": rate3,
            "rate4": rate4,
            "fixed": fixed_charge,
            "extra": extra_charge,
            "tax": tax_rate
        })

        st.success("Your tariff settings are saved!")
        st.rerun()


# =====================================================
# BILL CALCULATIONS
# =====================================================

def calculate_energy_charge(units):

    units = max(0.0, units)

    if units <= 100:
        return units * rate1

    elif units <= 200:
        return 100 * rate1 + (units - 100) * rate2

    elif units <= 400:
        return (
            100 * rate1
            + 100 * rate2
            + (units - 200) * rate3
        )

    else:
        return (
            100 * rate1
            + 100 * rate2
            + 200 * rate3
            + (units - 400) * rate4
        )


def calculate_bill(units, days):

    monthly_units = units * 30 / days

    energy = calculate_energy_charge(monthly_units) * days / 30
    fixed = fixed_charge * days / 30
    extra = extra_charge * days / 30

    subtotal = energy + fixed + extra
    tax = subtotal * tax_rate / 100

    return {
        "energy": energy,
        "fixed": fixed,
        "extra": extra,
        "tax": tax,
        "total": subtotal + tax
    }


# =====================================================
# MAIN DASHBOARD
# =====================================================

st.title("⚡ POWERMATE Dashboard")
st.write(f"Welcome, **{username}**!")
st.caption("Your personal home electricity monitoring system.")

# =====================================================
# ADD APPLIANCES
# =====================================================

st.divider()
st.header("🏠 Add Home Appliances")

with st.form("add_appliance_form"):

    col1, col2 = st.columns(2)

    with col1:

        appliance_name = st.selectbox(
            "Select Appliance",
            [
                "Fan",
                "LED Bulb",
                "Tube Light",
                "Television",
                "Refrigerator",
                "Air Conditioner",
                "Washing Machine",
                "Water Heater",
                "Computer",
                "Microwave",
                "Water Pump",
                "Custom Appliance"
            ]
        )

        custom_name = ""

        if appliance_name == "Custom Appliance":
            custom_name = st.text_input("Enter Appliance Name")

        wattage = st.number_input(
            "Power Rating (Watts)",
            min_value=1.0,
            value=75.0
        )

    with col2:

        quantity = st.number_input(
            "Number of Appliances",
            min_value=1,
            max_value=100,
            value=1
        )

        hours = st.number_input(
            "Hours Used Per Day",
            min_value=0.0,
            max_value=24.0,
            value=8.0,
            step=0.5
        )

    add_button = st.form_submit_button("➕ Add Appliance")

    if add_button:

        final_name = (
            custom_name.strip()
            if appliance_name == "Custom Appliance"
            else appliance_name
        )

        if not final_name:
            st.error("Please enter an appliance name.")

        else:
            add_appliance(
                user_id,
                final_name,
                wattage,
                int(quantity),
                hours
            )

            st.success("Appliance saved to your account!")
            st.rerun()


# =====================================================
# LOAD ONLY LOGGED-IN USER'S APPLIANCES
# =====================================================

df = load_appliances(user_id)

if not df.empty:

    # ---------------------------------------------
    # CONSUMPTION
    # ---------------------------------------------

    df["Daily Units"] = (
        df["wattage"] * df["quantity"] * df["hours"] / 1000
    )

    df["Weekly Units"] = df["Daily Units"] * 7
    df["Monthly Units"] = df["Daily Units"] * 30

    daily_units = df["Daily Units"].sum()
    weekly_units = df["Weekly Units"].sum()
    monthly_units = df["Monthly Units"].sum()

    # ---------------------------------------------
    # DASHBOARD METRICS
    # ---------------------------------------------

    st.divider()
    st.header("📊 Electricity Consumption Dashboard")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Appliances", len(df))
    c2.metric("Daily Units", f"{daily_units:.2f} kWh")
    c3.metric("Weekly Units", f"{weekly_units:.2f} kWh")
    c4.metric("Monthly Units", f"{monthly_units:.2f} kWh")

    # ---------------------------------------------
    # APPLIANCE TABLE
    # ---------------------------------------------

    st.divider()
    st.header("🔌 Appliance-wise Consumption")

    display_df = df.rename(columns={
        "id": "ID",
        "name": "Appliance",
        "wattage": "Power (W)",
        "quantity": "Quantity",
        "hours": "Hours/Day",
        "Daily Units": "Daily Units (kWh)",
        "Weekly Units": "Weekly Units (kWh)",
        "Monthly Units": "Monthly Units (kWh)"
    })

    st.dataframe(
        display_df[[
            "ID",
            "Appliance",
            "Power (W)",
            "Quantity",
            "Hours/Day",
            "Daily Units (kWh)",
            "Weekly Units (kWh)",
            "Monthly Units (kWh)"
        ]].round(2),
        use_container_width=True,
        hide_index=True
    )

    # ---------------------------------------------
    # DAILY, WEEKLY AND MONTHLY BILLS
    # ---------------------------------------------

    st.divider()
    st.header("💰 Daily, Weekly & Monthly Electricity Bills")

    daily_bill = calculate_bill(daily_units, 1)
    weekly_bill = calculate_bill(weekly_units, 7)
    monthly_bill = calculate_bill(monthly_units, 30)

    b1, b2, b3 = st.columns(3)

    with b1:
        st.subheader("☀️ Daily Bill")
        st.metric("Units Used", f"{daily_units:.2f} kWh")
        st.metric("Estimated Bill", f"₹{daily_bill['total']:.2f}")

    with b2:
        st.subheader("📅 Weekly Bill")
        st.metric("Units Used", f"{weekly_units:.2f} kWh")
        st.metric("Estimated Bill", f"₹{weekly_bill['total']:.2f}")

    with b3:
        st.subheader("🗓️ Monthly Bill")
        st.metric("Units Used", f"{monthly_units:.2f} kWh")
        st.metric("Estimated Bill", f"₹{monthly_bill['total']:.2f}")

    with st.expander("☀️ Daily Bill Breakdown"):
        st.write(f"Energy charge: ₹{daily_bill['energy']:.2f}")
        st.write(f"Fixed charges: ₹{daily_bill['fixed']:.2f}")
        st.write(f"Other charges: ₹{daily_bill['extra']:.2f}")
        st.write(f"Tax: ₹{daily_bill['tax']:.2f}")
        st.write(f"Total: ₹{daily_bill['total']:.2f}")

    with st.expander("📅 Weekly Bill Breakdown"):
        st.write(f"Energy charge: ₹{weekly_bill['energy']:.2f}")
        st.write(f"Fixed charges: ₹{weekly_bill['fixed']:.2f}")
        st.write(f"Other charges: ₹{weekly_bill['extra']:.2f}")
        st.write(f"Tax: ₹{weekly_bill['tax']:.2f}")
        st.write(f"Total: ₹{weekly_bill['total']:.2f}")

    with st.expander("🗓️ Monthly Bill Breakdown"):
        st.write(f"Energy charge: ₹{monthly_bill['energy']:.2f}")
        st.write(f"Fixed charges: ₹{monthly_bill['fixed']:.2f}")
        st.write(f"Other charges: ₹{monthly_bill['extra']:.2f}")
        st.write(f"Tax: ₹{monthly_bill['tax']:.2f}")
        st.write(f"Total: ₹{monthly_bill['total']:.2f}")

    # ---------------------------------------------
    # APPLIANCE COST
    # ---------------------------------------------

    st.divider()
    st.header("💵 Appliance-wise Monthly Cost")

    cost_df = df[["name", "Monthly Units"]].copy()

    cost_df["Estimated Monthly Cost (₹)"] = (
        cost_df["Monthly Units"] / monthly_units * monthly_bill["total"]
        if monthly_units > 0
        else 0
    )

    cost_df.rename(columns={
        "name": "Appliance",
        "Monthly Units": "Monthly Units (kWh)"
    }, inplace=True)

    st.dataframe(
        cost_df.round(2),
        use_container_width=True,
        hide_index=True
    )

    # ---------------------------------------------
    # CHARTS
    # ---------------------------------------------

    st.divider()
    st.header("📈 Electricity Usage Analysis")

    chart1, chart2 = st.columns(2)

    with chart1:
        fig1 = px.pie(
            df,
            names="name",
            values="Daily Units",
            title="Daily Usage by Appliance",
            hole=0.4
        )

        st.plotly_chart(fig1, use_container_width=True)

    with chart2:
        fig2 = px.bar(
            df,
            x="name",
            y="Monthly Units",
            color="name",
            title="Monthly Usage by Appliance"
        )

        st.plotly_chart(fig2, use_container_width=True)

    # ---------------------------------------------
    # SAVING SUGGESTIONS
    # ---------------------------------------------

    st.divider()
    st.header("💡 Electricity Saving Suggestions")

    highest = df.loc[df["Daily Units"].idxmax()]

    st.warning(
        f"Highest consuming appliance: {highest['name']} "
        f"using {highest['Daily Units']:.2f} units per day."
    )

    st.info(
        "Switch off unused appliances, reduce unnecessary usage "
        "and choose energy-efficient appliances to save electricity."
    )

    # ---------------------------------------------
    # EDIT APPLIANCE
    # ---------------------------------------------

    st.divider()
    st.header("✏️ Edit Appliance")

    edit_options = {
        f"{row['name']} (ID: {row['id']})": int(row["id"])
        for _, row in df.iterrows()
    }

    selected_edit = st.selectbox(
        "Select Appliance to Edit",
        list(edit_options.keys())
    )

    edit_id = edit_options[selected_edit]
    edit_row = df[df["id"] == edit_id].iloc[0]

    with st.form("edit_form"):

        edit_name = st.text_input(
            "Appliance Name",
            value=str(edit_row["name"])
        )

        edit_wattage = st.number_input(
            "Power Rating (Watts)",
            min_value=1.0,
            value=float(edit_row["wattage"])
        )

        edit_quantity = st.number_input(
            "Quantity",
            min_value=1,
            value=int(edit_row["quantity"])
        )

        edit_hours = st.number_input(
            "Hours Per Day",
            min_value=0.0,
            max_value=24.0,
            value=float(edit_row["hours"])
        )

        update_button = st.form_submit_button("💾 Update Appliance")

        if update_button:

            if edit_name.strip():

                update_appliance(
                    user_id,
                    edit_id,
                    edit_name.strip(),
                    edit_wattage,
                    int(edit_quantity),
                    edit_hours
                )

                st.success("Appliance updated!")
                st.rerun()

            else:
                st.error("Enter a valid appliance name.")

    # ---------------------------------------------
    # DELETE APPLIANCE
    # ---------------------------------------------

    st.divider()
    st.header("🗑️ Delete Appliance")

    selected_delete = st.selectbox(
        "Select Appliance to Delete",
        list(edit_options.keys()),
        key="delete_select"
    )

    if st.button("Delete Selected Appliance"):

        delete_appliance(
            user_id,
            edit_options[selected_delete]
        )

        st.success("Appliance deleted!")
        st.rerun()

    # ---------------------------------------------
    # CSV REPORT
    # ---------------------------------------------

    st.divider()
    st.header("📥 Download Electricity Report")

    csv = display_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download Full CSV Report",
        data=csv,
        file_name="POWERMATE_Report.csv",
        mime="text/csv"
    )

    st.success(
        "Your appliances and tariff settings are saved "
        "permanently in your account."
    )

else:

    st.info(
        "No appliances added yet. Add your first home appliance!"
    )


# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "⚡ POWERMATE | Smart Home Electricity Consumption & Billing System"
)

st.caption(
    "Sample tariff rates are provided. Actual bills depend on "
    "your electricity provider's tariff and billing rules."
)

st.caption(
    "Daily and weekly bills are estimates based on a 30-day "
    "monthly tariff projection."
)
