from reportlab.platypus import SimpleDocTemplate, Table
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import io
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

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=120)
def get_weekly(username):
    return api_call({
        "action": "history_weekly",
        "username": username
    })

def generate_weekly_pdf(data):

    buffer = io.BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    table_data = [
        ["Date", "User", "Product", "Qty", "Price", "Total", "Profit"]
    ]

    total_sales = 0
    total_profit = 0

    for row in data:
        
        total = int(row.get("total", 0))
        profit = int(row.get("profit", 0))

        total_sales += total
        total_profit += profit
        
        table_data.append([
            row.get("date", ""),
            row.get("user", ""),
            row.get("products_id", ""),
            row.get("qty", ""),
            row.get("price", ""),
            row.get("total", ""),
            row.get("profit", ""),
        ])

    table_data.append([
        "", "", "", "", "TOTAL",
        total_sales,
        total_profit
    ])
    
    table = Table(table_data)

    pdf.build([table])

    buffer.seek(0)

    return buffer

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

def edit_harga(username, product_id, harga_jual):
    return api_call({
        "action": "edit_harga",
        "username": username,
        "product_id": product_id,
        "harga_jual": harga_jual
    })


def edit_produk(username, product_id, name, harga_modal, harga_jual):
    return api_call({
        "action": "edit_produk",
        "username": username,
        "product_id": product_id,
        "name": name,
        "harga_modal": harga_modal,
        "harga_jual": harga_jual
    })

def delete_product(username, product_id):
    return api_call({
        "action": "delete_product",
        "username": username,
        "product_id": product_id
    })

def ambil_stok(username, product_id, qty):
    return api_call({
        "action": "ambil_stok",
        "username": username,
        "product_id": product_id,
        "qty": qty
    })

@st.cache_data(ttl=30)
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

# default menu
if "menu" not in st.session_state:
    st.session_state.menu = "Transaksi"


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

            product_dict = {p["name"]: p["id"] for p in products_data}

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

        if not weekly or weekly.get("status") != "success":
            st.warning("Data weekly belum tersedia.")
        else:

            if len(weekly.get("data", [])) == 0:
                st.info("Belum ada transaksi minggu ini.")
            else:

                st.metric("Transaksi", weekly.get("total_transaksi", 0))
                st.metric("Total Sales", weekly.get("total_sales", 0))
                st.metric("Total Profit", weekly.get("total_profit", 0))

                st.dataframe(weekly["data"])
            
            pdf = generate_weekly_pdf(weekly["data"])

            st.download_button(
                label="📄 Download PDF",
                data=pdf,
                file_name="laporan_mingguan.pdf",
                mime="application/pdf"
            )


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
                

    elif st.session_state.menu == "Edit Produk" and role == "boss":
        
        st.subheader("✏️ Edit Produk")

        products_data = products()

        if isinstance(products_data, list):
            
            product_dict = {p["name"]: p["id"] for p in products_data}

            selected = st.selectbox("Pilih Produk", list(product_dict.keys()))

            mode = st.radio(
                "Mode Edit",
                ["Edit Harga", "Edit Semua"],
                horizontal=True
            )

            if mode == "Edit Harga":

                harga = st.number_input("Harga Baru", min_value=0)

                if st.button("Update Harga"):

                    result = edit_harga(username, product_dict[selected], harga)

                    if result.get("status") == "success":
                        st.success("Harga berhasil diupdate")
                    else:
                        st.error(result)

            else:

                name = st.text_input("Nama Produk")
                modal = st.number_input("Harga Modal", min_value=0)
                jual = st.number_input("Harga Jual", min_value=0)

                if st.button("Update Produk"):

                    result = edit_produk(
                        username,
                        product_dict[selected],
                        name,
                        modal,
                        jual
                    )

                    if result.get("status") == "success":
                        st.success("Produk berhasil diupdate")
                    else:
                        st.error(result)

        else:
            st.error(products_data)

    
    elif st.session_state.menu == "Daftar Produk" and role == "boss":
        
        st.subheader("📦 Daftar Produk")

        products_data = products()

        if isinstance(products_data, list):
            

            table = []

            for p in products_data:
                

                table.append({
                    "ID": p["id"],
                    "Nama": p["name"],
                    "Modal": p["cost"],
                    "Harga Jual": p["price"],
                    "Stock Harian": p["harian_stock"]
                })

            st.dataframe(table, use_container_width=True)

        else:
            st.error(products_data)

    elif st.session_state.menu == "Hapus Produk" and role == "boss":

        st.subheader("🗑️ Hapus Produk")

        products_data = products()

        if isinstance(products_data, list):
            

            product_dict = {p["name"]: p["id"] for p in products_data}

            selected = st.selectbox(
                "Pilih Produk",
                list(product_dict.keys())
            )

            st.warning("Produk yang dihapus tidak bisa dikembalikan.")

            if st.button("Hapus Produk"):

                result = delete_product(
                    username,
                    product_dict[selected]
                )

                if result.get("status") == "success":
                    st.success("Produk berhasil dihapus")
                else:
                    st.error(result)

        else:
            st.error(products_data)
        
    
    elif st.session_state.menu == "Ambil Stok" and role == "boss":

        st.subheader("📤 Ambil Stok")

        products_data = products()

        if isinstance(products_data, list):

            product_dict = {p["name"]: p["id"] for p in products_data}

            selected = st.selectbox("Pilih Produk", list(product_dict.keys()))
            qty = st.number_input("Jumlah", min_value=1, step=1)

            if st.button("Ambil"):

                result = ambil_stok(username, product_dict[selected], qty)

                if result.get("status") == "success":
                    st.success("Stok berhasil dipindahkan")

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

                    get_store_status.clear()

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
        cols = st.columns(7)
    else:
        cols = st.columns(2)

    transaksi_btn = cols[0].button("🛒Transaksi")
    summary_btn = cols[1].button("📊P&L")

    if transaksi_btn:
        st.session_state.menu = "Transaksi"

    if summary_btn:
        st.session_state.menu = "Summary"

    if role == "boss":

        add_btn = cols[2].button("📦Tambah produk")

        
        weekly_btn = cols[3].button("📈Total Mingguan")
        ambil_btn = cols[4].button("📤Ambil stock")
        status_btn = cols[5].button("🏪Status Toko")
        produk_btn = cols[6].button("📋Daftar Produk")
        if add_btn:
            st.session_state.menu = "Add Product"

        if weekly_btn:
            st.session_state.menu = "Weekly"

        if ambil_btn:
            st.session_state.menu = "Ambil Stok"

        if status_btn:
            st.session_state.menu = "Status Toko"

        if produk_btn:
            st.session_state.menu = "Daftar Produk"
        
        st.markdown("---")

        if role == "boss":

            col1, col2 = st.columns(2)

        if col1.button("✏️ Edit Produk"):
            st.session_state.menu = "Edit Produk"

        if col2.button("🗑️ Hapus Produk"):
            st.session_state.menu = "Hapus Produk"


    # ===============================
    # LOGOUT
    # ===============================

    st.markdown("---")

    if st.button("Logout"):
        del st.session_state.user
        st.rerun()
