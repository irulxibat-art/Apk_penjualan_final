import streamlit as st
import pandas as pd
from supabase import create_client
from fpdf import FPDF
import datetime

# =======================
# SUPABASE CONFIG
# =======================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =======================
# SESSION
# =======================
if "user" not in st.session_state:
    st.session_state.user = None

# =======================
# AUTH
# =======================
def login(username, password):
    res = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
    return res.data[0] if res.data else None

# =======================
# LOGIN PAGE
# =======================
if not st.session_state.user:
    st.title("Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    
    if st.button("Login"):
        user = login(u, p)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Login gagal")

# =======================
# DASHBOARD
# =======================
else:
    role = st.session_state.user["role"]
    menu = st.sidebar.selectbox("Menu", ["Stock", "Penjualan", "History", "Logout"])

    # =======================
    # STOCK
    # =======================
    if menu == "Stock":
        st.header("Stock Gudang")

        data = supabase.table("products").select("*").execute().data
        df = pd.DataFrame(data)
        st.dataframe(df)

        if role == "boss":
            st.subheader("Tambah Produk")
            sku = st.text_input("SKU")
            name = st.text_input("Nama")
            cost = st.number_input("Modal")
            price = st.number_input("Harga")

            if st.button("Tambah"):
                supabase.table("products").insert({
                    "sku": sku,
                    "name": name,
                    "cost": cost,
                    "price": price
                }).execute()
                st.success("Produk ditambah")
                st.rerun()

    # =======================
    # PENJUALAN
    # =======================
    elif menu == "Penjualan":
        st.header("Penjualan")

        products = supabase.table("products").select("*").execute().data
        df = pd.DataFrame(products)

        prod = st.selectbox("Produk", df["name"])
        qty = st.number_input("Qty", 1)

        row = df[df["name"] == prod].iloc[0]
        total = row["price"] * qty
        profit = (row["price"] - row["cost"]) * qty

        if st.button("Simpan"):
            supabase.table("sales").insert({
                "product_id": int(row["id"]),
                "qty": qty,
                "total": total,
                "profit": profit
            }).execute()
            st.success("Transaksi tersimpan")

    # =======================
    # HISTORY
    # =======================
    elif menu == "History":
        st.header("History Penjualan")

        sales = supabase.table("sales").select("*").execute().data
        df = pd.DataFrame(sales)

        if df.empty:
            st.warning("Belum ada data")
        else:
            today = datetime.date.today()
            df["date"] = pd.to_datetime(df["sold_at"]).dt.date

            daily = df[df["date"] == today]

            st.subheader("History Harian")
            st.dataframe(daily)

            total = daily["total"].sum()
            profit = daily["profit"].sum()

            if role == "boss":
                st.success(f"Total: {total}")
                st.success(f"P&L: {profit}")
            else:
                st.info(f"Total Penjualan: {total}")

            # PDF untuk Boss
            if role == "boss":
                if st.button("Export PDF"):
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", size=10)
                    pdf.cell(0, 10, f"History {today}", ln=True)

                    for _, r in daily.iterrows():
                        pdf.cell(0, 8, f"ID {r['id']} - Total {r['total']}", ln=True)

                    file = f"history_{today}.pdf"
                    pdf.output(file)

                    with open(file, "rb") as f:
                        supabase.storage.from_("pdf").upload(file, f)

                    st.success("PDF tersimpan di Supabase Storage")

    # =======================
    # LOGOUT
    # =======================
    elif menu == "Logout":
        st.session_state.user = None
        st.rerun()
