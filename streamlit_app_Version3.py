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


def get_products():
    return api_call({
        "action": "get_products"
    })


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


def ambil_stok_harian(username, product_id, qty):
    return api_call({
        "action": "ambil_stok",
        "username": username,
        "product_id": product_id,
        "qty": qty
    })


def get_store_status():
    return api_call({
        "action": "get_store_status"
    })


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
            st.rerun()
        else:
            st.error("Login gagal")

else:

    user = st.session_state.user
    username = user["username"]
    role = user["role"]

    if "menu" not in st.session_state:
        st.session_state.menu = "Transaksi"

    # =====================================
    # PAGE: TRANSAKSI
    # =====================================
    if st.session_state.menu == "Transaksi":

        st.subheader("🛒 Transaksi Penjualan")

        products_data = get_products()

        if products_data.get("status") == "success":

            products = products_data["data"]

            product_dict = {
                p["name"]: p["id"] for p in products
            }

            selected_name = st.selectbox(
                "Pilih Produk",
                list(product_dict.keys())
            )

            qty = st.number_input("Qty", min_value=1, step=1)

            if st.button("Proses Transaksi"):
                product_id = product_dict[selected_name]

                result = jual_produk(username, product_id, qty)

                if result.get("status") == "success":
                    st.success("Transaksi berhasil")
                else:
                    st.error(result.get("message", "Gagal transaksi"))
        else:
            st.error("Gagal mengambil produk")

    # =====================================
    # PAGE: SUMMARY
    # =====================================
    elif st.session_state.menu == "Summary":

        st.subheader("📊 Total Hari Ini")

        summary = get_summary_today(username)

        if summary.get("status") == "success":
            st.metric("Total Sales", f"Rp {summary['total_sales']:,}")
            st.metric("Total Profit", f"Rp {summary['total_profit']:,}")
            st.metric("Total Transaksi", summary["total_transaksi"])
        else:
            st.error("Gagal mengambil data")

    # =====================================
    # PAGE: WEEKLY (BOSS)
    # =====================================
    elif st.session_state.menu == "Weekly" and role == "boss":

        st.subheader("📈 History Weekly")

        weekly = get_weekly(username)

        if weekly.get("status") == "success":
            st.metric("Sales Mingguan", f"Rp {weekly['total_sales']:,}")
            st.metric("Profit Mingguan", f"Rp {weekly['total_profit']:,}")
            st.metric("Total Transaksi", weekly["total_transaksi"])

            if weekly.get("data"):
                st.json(weekly["data"])
        else:
            st.error("Gagal mengambil data")

    # =====================================
    # PAGE: ADD PRODUCT (BOSS)
    # =====================================
    elif st.session_state.menu == "Add Product" and role == "boss":

        st.subheader("📦 Tambah Produk")

        new_id = st.text_input("Product ID")
        new_name = st.text_input("Nama Produk")
        harga_modal = st.number_input("Harga Modal", min_value=0, step=1000)
        harga_jual = st.number_input("Harga Jual", min_value=0, step=1000)
        stok_awal = st.number_input("Stok Awal", min_value=0, step=1)

        if st.button("Tambah Produk"):
            result = add_product(
                username,
                new_id,
                new_name,
                harga_modal,
                harga_jual,
                stok_awal
            )

            if result.get("status") == "success":
                st.success("Produk berhasil ditambahkan")
            else:
                st.error(result.get("message", "Gagal menambahkan produk"))

    # =====================================
    # PAGE: AMBIL STOK (BOSS)
    # =====================================
    elif st.session_state.menu == "Ambil Stok" and role == "boss":

        st.subheader("📤 Ambil Stok Harian")

        if st.button("Ambil Stok"):
            result = ambil_stok_harian(username)

            if result.get("status") == "success":
                st.success("Stok berhasil diambil")
            else:
                st.error(result.get("message", "Gagal ambil stok"))

    # =====================================
    # PAGE: STATUS TOKO
    # =====================================

    elif st.session_state.menu == "Status Toko" and role == "boss":

        st.subheader("🏪 Status Toko")

        status_data = get_store_status()

        if status_data.get("status") == "success":
            current_status = status_data["store_status"]

            if current_status == "open":
                st.success("Toko Sedang BUKA")
            else:
                st.error("Toko Sedang TUTUP")

            pilihan = st.radio(
                "Ubah Status",
                ["open", "closed"],
                horizontal=True,
                index=0 if current_status == "open" else 1
            )

            if st.button("Simpan Perubahan"):
                result = set_store_status(username, pilihan)

                if result.get("status") == "success":
                    st.success("Status berhasil diubah")
                    st.rerun()
                else:
                    st.error("Gagal mengubah status")
        else:
            st.error("Gagal mengambil status toko")

    # ==========================
    # BOTTOM NAVIGATION
    # ==========================

    st.markdown("---")

    if role == "boss":
        menu_cols = st.columns(6)
    else:
        menu_cols = st.columns(2)

    if menu_cols[0].button("🛒 transaksi", use_container_width=True):
        st.session_state.menu = "Transaksi"

    if menu_cols[1].button("📊 Summary", use_container_width=True):
        st.session_state.menu = "Summary"

    if role == "boss":
        if menu_cols[2].button("📦 tambah product", use_container_width=True):
            st.session_state.menu = "Add Product"

        if menu_cols[3].button("📈 weekly", use_container_width=True):
            st.session_state.menu = "Weekly"

        if menu_cols[4].button("📤 ambil stock", use_container_width=True):
            st.session_state.menu = "Ambil Stok"

        if menu_cols[5].button("🏪 status toko", use_container_width=True):
            st.session_state.menu = "Status Toko"


    # =====================================
    # LOGOUT
    # =====================================
    st.divider()
    if st.button("Logout"):
        del st.session_state.user
        st.rerun()
