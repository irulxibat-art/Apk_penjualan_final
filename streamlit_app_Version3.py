import streamlit as st
import requests

# =====================================
# CONFIG
# =====================================
BASE_URL = st.secrets["BASE_URL"]

def api_call(params):
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        return response.json()
    except:
        return {"status": "error", "message": "API tidak dapat diakses"}

# =====================================
# API FUNCTIONS
# =====================================
def login(username, password):
    return api_call({
        "action": "login",
        "username": username,
        "password": password
    })

def products():
    return api_call({"action": "products"})

def jual_produk(username, product_id, qty):
    return api_call({
        "action": "jual",
        "username": username,
        "product_id": product_id,
        "qty": qty
    })

def get_summary_today(username):
    return api_call({
        "action": "summary_today",
        "username": username
    })

def get_weekly(username):
    return api_call({
        "action": "history_weekly",
        "username": username
    })

def add_product(username, product_id, name, harga_modal, harga_jual, stok_awal):
    return api_call({
        "action": "add_product",
        "username": username,
        "product_id": product_id,
        "name": name,
        "harga_modal": harga_modal,
        "harga_jual": harga_jual,
        "stok_awal": stok_awal
    })

def ambil_stok(username, product_id, qty):
    return api_call({
        "action": "ambil_stok",
        "username": username,
        "product_id": product_id,
        "qty": qty
    })

def get_store_status():
    return api_call({"action": "get_store_status"})

def set_store_status(username, status):
    return api_call({
        "action": "set_store_status",
        "username": username,
        "status": status
    })

# =====================================
# UI CONFIG
# =====================================
st.set_page_config(page_title="Aplikasi Penjualan", layout="centered")
st.title("📊 Aplikasi Penjualan")

# =====================================
# LOGIN
# =====================================
if "user" not in st.session_state:

    st.subheader("Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        result = login(u, p)
        if result.get("status") == "success":
            st.session_state.user = result
            st.session_state.menu = "Transaksi"
            st.rerun()
        else:
            st.error("Login gagal")

# =====================================
# AFTER LOGIN
# =====================================
else:

    user = st.session_state.user
    username = user["username"]
    role = user["role"]

    # ===============================
    # PAGE SWITCH
    # ===============================

    if st.session_state.menu == "Transaksi":

        st.subheader("🛒 Transaksi")

        products_data = products()

        if isinstance(products_data, list):

            product_dict = {
                p["name"]: p["id"] for p in products_data
            }

            selected = st.selectbox("Pilih Produk", list(product_dict.keys()))
            qty = st.number_input("Qty", min_value=1, step=1)

            if st.button("Proses"):
                result = jual_produk(username, product_dict[selected], qty)

                if result.get("status") == "success":
                    st.success("Transaksi berhasil")
                else:
                    st.error(result)

        else:
            st.error(products_data)

    elif st.session_state.menu == "Summary":

        st.subheader("📊 Summary Hari Ini")

        summary = get_summary_today(username)

        if summary.get("status") == "success":
            st.metric("Total Sales", f"Rp {summary['total_sales']:,}")
            st.metric("Total Profit", f"Rp {summary['total_profit']:,}")
            st.metric("Total Transaksi", summary["total_transaksi"])
        else:
            st.error(summary)

    elif st.session_state.menu == "Weekly" and role == "boss":

        st.subheader("📈 Weekly")

        weekly = get_weekly(username)

        if weekly.get("status") == "success":
            st.metric("Sales", f"Rp {weekly['total_sales']:,}")
            st.metric("Profit", f"Rp {weekly['total_profit']:,}")
            st.metric("Transaksi", weekly["total_transaksi"])
        else:
            st.error(weekly)

    elif st.session_state.menu == "Add Product" and role == "boss":

        st.subheader("📦 Tambah Produk")

        pid = st.text_input("Product ID")
        name = st.text_input("Nama")
        modal = st.number_input("Harga Modal", min_value=0)
        jual = st.number_input("Harga Jual", min_value=0)
        stok = st.number_input("Stok Awal", min_value=0)

        if st.button("Tambah"):
            result = add_product(username, pid, name, modal, jual, stok)

            if result.get("status") == "success":
                st.success("Berhasil ditambahkan")
            else:
                st.error(result)

    elif st.session_state.menu == "Ambil Stok" and role == "boss":

        st.subheader("📤 Ambil Stok")

        products_data = products()

        if isinstance(products_data, list):

            product_dict = {
                p["name"]: p["id"] for p in products_data
            }

            selected = st.selectbox("Pilih Produk", list(product_dict.keys()))
            qty = st.number_input("Jumlah", min_value=1, step=1)

            if st.button("Ambil"):
                result = ambil_stok(username, product_dict[selected], qty)

                if result.get("status") == "success":
                    st.success("Stok berhasil dipindahkan")
                    st.rerun()
                else:
                    st.error(result)

        else:
            st.error(products_data)

    elif st.session_state.menu == "Status Toko" and role == "boss":

        st.subheader("🏪 Status Toko")

        status_data = get_store_status()

        if status_data.get("status") == "success":

            current = status_data["store_status"]

            if current == "open":
                st.success("Toko BUKA")
            else:
                st.error("Toko TUTUP")

            pilihan = st.radio(
                "Ubah Status",
                ["open", "closed"],
                horizontal=True,
                index=0 if current == "open" else 1
            )

            if st.button("Simpan"):
                result = set_store_status(username, pilihan)

                if result.get("status") == "success":
                    st.success("Berhasil diubah")
                    st.rerun()
                else:
                    st.error(result)
        else:
            st.error(status_data)

    # ===============================
    # BOTTOM NAVIGATION
    # ===============================
    st.markdown("---")

    if role == "boss":
        cols = st.columns(6)
    else:
        cols = st.columns(2)

    if cols[0].button("🛒Transaksi"):
        st.session_state.menu = "Transaksi"

    if cols[1].button("📊P&L"):
        st.session_state.menu = "Summary"

    if role == "boss":
        if cols[2].button("📦Tambah produk"):
            st.session_state.menu = "Add Product"
        if cols[3].button("📈Total Mingguan"):
            st.session_state.menu = "Weekly"
        if cols[4].button("📤Ambil stock"):
            st.session_state.menu = "Ambil Stok"
        if cols[5].button("🏪Status Toko"):
            st.session_state.menu = "Status Toko"

    # ===============================
    # LOGOUT
    # ===============================
    st.markdown("---")
    if st.button("Logout"):
        del st.session_state.user
        st.rerun()
