import os
import json
import datetime
from flask import Flask, jsonify, request, render_template, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Database Configuration for iPos 4
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres.zbwaogqsukasjqosuepf:lIsnIiPzPBbcY1WK@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 5444))
DB_DATABASE = os.environ.get("DB_DATABASE", "i4_xaptk")
DB_USERNAME = os.environ.get("DB_USERNAME", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "2356988")

# Timezone Configuration (WIB / GMT+7)
WIB = datetime.timezone(datetime.timedelta(hours=7))

def get_wib_now():
    return datetime.datetime.now(WIB)

def get_wib_today_str():
    return get_wib_now().strftime("%Y-%m-%d")

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_DATABASE,
            user=DB_USERNAME,
            password=DB_PASSWORD
        )
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Asia/Jakarta';")
    return conn

def determine_cara_bayar(row):
    if row.get("carabayar") and str(row["carabayar"]).strip():
        return str(row["carabayar"]).strip()
    methods = []
    if float(row.get("jmltunai", 0) or 0) > 0: methods.append("TUNAI")
    if float(row.get("jmldebit", 0) or 0) > 0: methods.append("DEBIT")
    if float(row.get("jmlkk", 0) or 0) > 0: methods.append("KKREDIT")
    if float(row.get("jmlemoney", 0) or 0) > 0: methods.append("EMONEY")
    if float(row.get("jmldeposit", 0) or 0) > 0: methods.append("DEPOSIT")
    if float(row.get("jmlkredit", 0) or 0) > 0: methods.append("KREDIT")
    return ", ".join(methods) if methods else "TUNAI"

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,ngrok-skip-browser-warning'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def serve_sw():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")

ASSETLINKS_CONTENT = """[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.ipos4.dashboardowner",
      "sha256_cert_fingerprints": [
        "58:02:56:F1:9B:5B:BC:28:67:3F:6C:B6:21:8F:8D:ED:E7:C4:51:38:C2:4E:7D:50:9B:A3:BB:D0:29:B4:F6:3E"
      ]
    }
  }
]"""

@app.route("/.well-known/assetlinks.json")
def serve_assetlinks():
    path = os.path.join("static", ".well-known", "assetlinks.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return app.response_class(f.read(), mimetype="application/json")
    return app.response_class(ASSETLINKS_CONTENT, mimetype="application/json")

@app.route("/download-apk")
@app.route("/Bos-Cek-Omset.apk")
@app.route("/Dashboard-Owner.apk")
def download_apk():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    apk_files = [f for f in os.listdir(static_dir) if f.startswith("Omset-v") and f.endswith(".apk")]
    if apk_files:
        apk_files.sort()
        apk_file = apk_files[-1]
    else:
        apk_file = "Omset-v1.0.0.apk"
    return send_from_directory("static", apk_file, as_attachment=True, download_name=apk_file)

@app.route("/<apk_name>.apk")
def download_specific_apk(apk_name):
    target = f"{apk_name}.apk"
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(os.path.join(static_dir, target)):
        return send_from_directory("static", target, as_attachment=True, download_name=target)
    return download_apk()

@app.route("/api", methods=["GET"])
def api_info():
    return jsonify({
        "status": "online",
        "service": "iPos 4 Owner API",
        "database": DB_DATABASE,
        "endpoints": [
            "/api/omset",
            "/api/setoran-kasir",
            "/api/kasir-users"
        ]
    })

@app.route("/api/kasir-users", methods=["GET"])
def get_kasir_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT DISTINCT user1
            FROM tbl_ikhd
            WHERE user1 IS NOT NULL AND TRIM(user1) <> ''
            ORDER BY user1 ASC
        """)
        users = [r["user1"] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e), "users": []}), 500

@app.route("/api/setoran-kasir", methods=["GET"])
def get_setoran_kasir():
    try:
        target_date = request.args.get("tanggal")
        if not target_date:
            target_date = get_wib_today_str()
        
        target_user = request.args.get("user")

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Format tanggal display (dd/mm/yy)
        try:
            dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
            tgl_formatted = dt.strftime("%d/%m/%y")
        except:
            tgl_formatted = target_date

        jam_cetak = get_wib_now().strftime("%d/%m/%y %H:%M")

        if target_user and target_user.upper() not in ["SEMUA", "ALL", ""]:
            query = """
                SELECT
                    user1,
                    COUNT(*) AS jml_transaksi,
                    COALESCE(SUM(potfaktur), 0) AS tot_potongan,
                    COALESCE(SUM(pajak), 0) AS tot_pajak,
                    COALESCE(SUM(biayalain), 0) AS tot_biaya,
                    COALESCE(SUM(totalakhir), 0) AS total,
                    COALESCE(SUM(jmltunai), 0) AS bayar_tunai,
                    COALESCE(SUM(jmlkredit), 0) AS bayar_kredit,
                    COALESCE(SUM(jmldebit), 0) AS bayar_debit,
                    COALESCE(SUM(jmlkk), 0) AS bayar_kkredit,
                    COALESCE(SUM(jmlemoney), 0) AS bayar_emoney,
                    COALESCE(SUM(jmldeposit), 0) AS bayar_deposit,
                    COALESCE(SUM(GREATEST(0, (jmltunai + jmldebit + jmlkk + jmlemoney + jmldeposit + jmlkredit) - totalakhir)), 0) AS kembalian,
                    COALESCE(MIN(kodekantor), 'UTM') AS dept_gdng
                FROM tbl_ikhd
                WHERE tanggal::date = %s AND user1 = %s
                GROUP BY user1
            """
            params = [target_date, target_user]
        else:
            query = """
                SELECT
                    user1,
                    COUNT(*) AS jml_transaksi,
                    COALESCE(SUM(potfaktur), 0) AS tot_potongan,
                    COALESCE(SUM(pajak), 0) AS tot_pajak,
                    COALESCE(SUM(biayalain), 0) AS tot_biaya,
                    COALESCE(SUM(totalakhir), 0) AS total,
                    COALESCE(SUM(jmltunai), 0) AS bayar_tunai,
                    COALESCE(SUM(jmlkredit), 0) AS bayar_kredit,
                    COALESCE(SUM(jmldebit), 0) AS bayar_debit,
                    COALESCE(SUM(jmlkk), 0) AS bayar_kkredit,
                    COALESCE(SUM(jmlemoney), 0) AS bayar_emoney,
                    COALESCE(SUM(jmldeposit), 0) AS bayar_deposit,
                    COALESCE(SUM(GREATEST(0, (jmltunai + jmldebit + jmlkk + jmlemoney + jmldeposit + jmlkredit) - totalakhir)), 0) AS kembalian,
                    COALESCE(MIN(kodekantor), 'UTM') AS dept_gdng
                FROM tbl_ikhd
                WHERE tanggal::date = %s
                GROUP BY user1
                ORDER BY total DESC
            """
            params = [target_date]

        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        slips = []
        for r in rows:
            total = float(r["total"])
            bayar_tunai = float(r["bayar_tunai"])
            kembalian = float(r["kembalian"])
            bayar_kredit = float(r["bayar_kredit"])
            bayar_debit = float(r["bayar_debit"])
            bayar_kkredit = float(r["bayar_kkredit"])
            bayar_emoney = float(r["bayar_emoney"])
            bayar_deposit = float(r["bayar_deposit"])

            ret_tunai = 0.0
            ret_kredit = 0.0
            ret_deposit = 0.0
            tot_retur = 0.0

            tunai_bersih = max(0.0, (bayar_tunai - kembalian) - ret_tunai)
            kredit_bersih = max(0.0, bayar_kredit - ret_kredit)
            deposit_bersih = max(0.0, bayar_deposit - ret_deposit)
            total_setelah_retur = max(0.0, total - tot_retur)

            slips.append({
                "periode": f"{tgl_formatted} s/d {tgl_formatted}",
                "user": (r["user1"] or "KASIR").upper(),
                "dept_gdng": r["dept_gdng"] or "UTM",
                "jam_cetak": jam_cetak,
                "jml_transaksi": int(r["jml_transaksi"]),
                "tot_potongan": float(r["tot_potongan"]),
                "tot_pajak": float(r["tot_pajak"]),
                "tot_biaya": float(r["tot_biaya"]),
                "total": total,
                "bayar_tunai": bayar_tunai,
                "bayar_kredit": bayar_kredit,
                "bayar_debit": bayar_debit,
                "bayar_kkredit": bayar_kkredit,
                "bayar_emoney": bayar_emoney,
                "bayar_deposit": bayar_deposit,
                "kembalian": kembalian,
                "tot_deposit": 0.0,
                "tot_donasi": 0.0,
                "retur": {
                    "ret_tunai": ret_tunai,
                    "ret_kredit": ret_kredit,
                    "ret_deposit": ret_deposit,
                    "tot_retur": tot_retur
                },
                "setelah_retur": {
                    "total": total_setelah_retur,
                    "tunai": tunai_bersih,
                    "kredit": kredit_bersih,
                    "deposit": deposit_bersih
                }
            })

        # Jika tidak ada transaksi sama sekali pada tanggal ini
        if not slips:
            slips.append({
                "periode": f"{tgl_formatted} s/d {tgl_formatted}",
                "user": "-",
                "dept_gdng": "UTM",
                "jam_cetak": jam_cetak,
                "jml_transaksi": 0,
                "tot_potongan": 0.0,
                "tot_pajak": 0.0,
                "tot_biaya": 0.0,
                "total": 0.0,
                "bayar_tunai": 0.0,
                "bayar_kredit": 0.0,
                "bayar_debit": 0.0,
                "bayar_kkredit": 0.0,
                "bayar_emoney": 0.0,
                "bayar_deposit": 0.0,
                "kembalian": 0.0,
                "tot_deposit": 0.0,
                "tot_donasi": 0.0,
                "retur": {
                    "ret_tunai": 0.0,
                    "ret_kredit": 0.0,
                    "ret_deposit": 0.0,
                    "tot_retur": 0.0
                },
                "setelah_retur": {
                    "total": 0.0,
                    "tunai": 0.0,
                    "kredit": 0.0,
                    "deposit": 0.0
                }
            })

        first_slip = slips[0]
        return jsonify({
            "status": "success",
            "tanggal": target_date,
            "tanggal_display": tgl_formatted,
            "total_kasir": len([s for s in slips if s["jml_transaksi"] > 0]),
            "slips": slips,
            "periode": first_slip["periode"],
            "user": first_slip["user"],
            "dept_gdng": first_slip["dept_gdng"],
            "jam_cetak": first_slip["jam_cetak"],
            "jml_transaksi": first_slip["jml_transaksi"],
            "total": first_slip["total"],
            "bayar_tunai": first_slip["bayar_tunai"],
            "kembalian": first_slip["kembalian"],
            "retur": first_slip["retur"],
            "setelah_retur": first_slip["setelah_retur"]
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route("/api/rekap-kasir", methods=["GET"])
def get_rekap_kasir():
    try:
        target_date = request.args.get("tanggal")
        if not target_date:
            target_date = get_wib_today_str()

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                COALESCE(user1, 'UNKNOWN') AS kasir,
                COUNT(*) AS jml_transaksi,
                COALESCE(SUM(totalakhir), 0) AS total_omset
            FROM tbl_ikhd
            WHERE tanggal::date = %s
            GROUP BY user1
            ORDER BY total_omset DESC
        """, (target_date,))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        total_day_omset = sum(float(r["total_omset"]) for r in rows)
        total_day_tx = sum(int(r["jml_transaksi"]) for r in rows)

        try:
            dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
            tgl_formatted = dt.strftime("%d/%m/%y")
        except:
            tgl_formatted = target_date

        rekap = []
        for r in rows:
            omset = float(r["total_omset"])
            pct = (omset / total_day_omset * 100) if total_day_omset > 0 else 0.0
            rekap.append({
                "kasir": r["kasir"],
                "jml_transaksi": int(r["jml_transaksi"]),
                "total_omset": omset,
                "persen": round(pct, 1)
            })

        return jsonify({
            "status": "success",
            "tanggal": target_date,
            "tanggal_display": tgl_formatted,
            "total_omset": total_day_omset,
            "total_transaksi": total_day_tx,
            "rekap": rekap
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route("/api/chart-sales", methods=["GET"])
def get_chart_sales():
    try:
        periode = request.args.get("periode", "minggu").lower()
        custom_date = request.args.get("tanggal")
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        data = []
        title = "Penjualan 1 Minggu"
        
        if periode == "bulan":
            title = "Penjualan 1 Bulan"
            cur.execute("""
                SELECT tanggal::date::text AS tanggal, COALESCE(SUM(totalakhir), 0) AS total
                FROM tbl_ikhd
                WHERE EXTRACT(MONTH FROM tanggal) = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND EXTRACT(YEAR FROM tanggal) = EXTRACT(YEAR FROM CURRENT_DATE)
                GROUP BY tanggal::date
                ORDER BY tanggal::date ASC;
            """)
            for r in cur.fetchall():
                try:
                    dt = datetime.datetime.strptime(r["tanggal"], "%Y-%m-%d")
                    lbl = dt.strftime("%d/%m")
                except:
                    lbl = r["tanggal"]
                data.append({"label": lbl, "total": float(r["total"])})
                
        elif periode == "tahun":
            title = "Penjualan 1 Tahun"
            cur.execute("""
                SELECT TO_CHAR(tanggal, 'YYYY-MM') AS bln, COALESCE(SUM(totalakhir), 0) AS total
                FROM tbl_ikhd
                WHERE EXTRACT(YEAR FROM tanggal) = EXTRACT(YEAR FROM CURRENT_DATE)
                GROUP BY TO_CHAR(tanggal, 'YYYY-MM')
                ORDER BY bln ASC;
            """)
            month_names = {
                "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "Mei", "06": "Jun",
                "07": "Jul", "08": "Agu", "09": "Sep", "10": "Okt", "11": "Nov", "12": "Des"
            }
            for r in cur.fetchall():
                m_part = r["bln"].split("-")[-1]
                lbl = month_names.get(m_part, m_part)
                data.append({"label": lbl, "total": float(r["total"])})
                
        elif periode == "tanggal" and custom_date:
            try:
                dt = datetime.datetime.strptime(custom_date, "%Y-%m-%d")
                tgl_disp = dt.strftime("%d/%m/%y")
            except:
                tgl_disp = custom_date
            title = f"Penjualan Tanggal {tgl_disp}"
            cur.execute("""
                SELECT EXTRACT(HOUR FROM tanggal)::int AS jam, COALESCE(SUM(totalakhir), 0) AS total
                FROM tbl_ikhd
                WHERE tanggal::date = %s
                GROUP BY EXTRACT(HOUR FROM tanggal)
                ORDER BY jam ASC;
            """, (custom_date,))
            for r in cur.fetchall():
                lbl = f"{int(r['jam']):02d}:00"
                data.append({"label": lbl, "total": float(r["total"])})
                
        else: # default: minggu (7 hari terakhir)
            periode = "minggu"
            title = "Penjualan 1 Minggu"
            cur.execute("""
                SELECT tanggal::date::text AS tanggal, COALESCE(SUM(totalakhir), 0) AS total
                FROM tbl_ikhd
                WHERE tanggal::date >= CURRENT_DATE - INTERVAL '6 days' AND tanggal::date <= CURRENT_DATE
                GROUP BY tanggal::date
                ORDER BY tanggal::date ASC;
            """)
            rows = cur.fetchall()
            if not rows:
                cur.execute("""
                    SELECT tanggal::date::text AS tanggal, COALESCE(SUM(totalakhir), 0) AS total
                    FROM tbl_ikhd
                    WHERE tanggal::date >= (SELECT MAX(tanggal::date) FROM tbl_ikhd) - INTERVAL '6 days'
                      AND tanggal::date <= (SELECT MAX(tanggal::date) FROM tbl_ikhd)
                    GROUP BY tanggal::date
                    ORDER BY tanggal::date ASC;
                """)
                rows = cur.fetchall()
            for r in rows:
                try:
                    dt = datetime.datetime.strptime(r["tanggal"], "%Y-%m-%d")
                    lbl = dt.strftime("%d/%m")
                except:
                    lbl = r["tanggal"]
                data.append({"label": lbl, "total": float(r["total"])})
                
        cur.close()
        conn.close()

        total_penjualan = sum(float(d["total"]) for d in data)
        formatted_total = f"Rp. {int(round(total_penjualan)):,}".replace(",", ".")
        full_title = f"{title} {formatted_total}"

        return jsonify({
            "status": "success",
            "periode": periode,
            "title": full_title,
            "base_title": title,
            "total": total_penjualan,
            "formatted_total": formatted_total,
            "data": data
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/transaksi-realtime", methods=["GET"])
def get_transaksi_realtime():
    try:
        search = request.args.get("search", "").strip()
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT
                hd.notransaksi,
                TO_CHAR(hd.tanggal, 'DD/MM/YY HH24:MI') AS waktu,
                hd.user1 AS kasir,
                COALESCE(hd.kodesupel, 'UMUM') AS customer,
                COALESCE(hd.totalitem, 0) AS totalitem,
                COALESCE(hd.totalakhir, 0) AS totalakhir,
                COALESCE(hd.jmltunai, 0) AS jmltunai,
                COALESCE(hd.jmldebit, 0) AS jmldebit,
                COALESCE(hd.jmlkk, 0) AS jmlkk,
                COALESCE(hd.jmlemoney, 0) AS jmlemoney,
                COALESCE(hd.jmldeposit, 0) AS jmldeposit,
                COALESCE(hd.jmlkredit, 0) AS jmlkredit,
                hd.carabayar
            FROM tbl_ikhd hd
            WHERE (%s = '' OR hd.notransaksi ILIKE %s OR hd.user1 ILIKE %s)
            ORDER BY hd.tanggal DESC, hd.notransaksi DESC
            LIMIT %s OFFSET %s
        """
        search_param = f"%{search}%"
        cur.execute(query, (search, search_param, search_param, limit, offset))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        transaksi = []
        for r in rows:
            transaksi.append({
                "notransaksi": r["notransaksi"],
                "waktu": r["waktu"],
                "kasir": r["kasir"] or "KASIR",
                "customer": r["customer"],
                "totalitem": int(r["totalitem"]),
                "totalakhir": float(r["totalakhir"]),
                "carabayar": determine_cara_bayar(r)
            })
            
        return jsonify({
            "status": "success",
            "total": len(transaksi),
            "limit": limit,
            "offset": offset,
            "has_more": len(transaksi) >= limit,
            "transaksi": transaksi,
            "data": transaksi
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/transaksi-detail/<path:notransaksi>", methods=["GET"])
def get_transaksi_detail(notransaksi):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT
                notransaksi,
                TO_CHAR(tanggal, 'DD/MM/YY HH24:MI') AS waktu,
                user1 AS kasir,
                COALESCE(kodekantor, 'UTM') AS dept_gdng,
                COALESCE(kodesupel, 'UMUM') AS customer,
                COALESCE(totalitem, 0) AS totalitem,
                COALESCE(subtotal, 0) AS subtotal,
                COALESCE(potfaktur, 0) AS potfaktur,
                COALESCE(pajak, 0) AS pajak,
                COALESCE(biayalain, 0) AS biayalain,
                COALESCE(totalakhir, 0) AS totalakhir,
                COALESCE(jmltunai, 0) AS jmltunai,
                COALESCE(jmldebit, 0) AS jmldebit,
                COALESCE(jmlkk, 0) AS jmlkk,
                COALESCE(jmlemoney, 0) AS jmlemoney,
                COALESCE(jmldeposit, 0) AS jmldeposit,
                COALESCE(jmlkredit, 0) AS jmlkredit,
                COALESCE(GREATEST(0, (jmltunai + jmldebit + jmlkk + jmlemoney + jmldeposit + jmlkredit) - totalakhir), 0) AS kembalian,
                carabayar
            FROM tbl_ikhd
            WHERE notransaksi = %s
        """, (notransaksi,))
        hd = cur.fetchone()
        if not hd:
            cur.close()
            conn.close()
            return jsonify({"status": "error", "message": "Faktur tidak ditemukan"}), 404
            
        cur.execute("""
            SELECT
                dt.nobaris,
                dt.kodeitem,
                COALESCE(it.namaitem, dt.kodeitem) AS namaitem,
                COALESCE(dt.jumlah, 0) AS jumlah,
                COALESCE(dt.satuan, 'PCS') AS satuan,
                COALESCE(dt.harga, 0) AS harga,
                COALESCE(dt.potongan, 0) AS potongan,
                COALESCE(dt.total, 0) AS total
            FROM tbl_ikdt dt
            LEFT JOIN tbl_item it ON dt.kodeitem = it.kodeitem
            WHERE dt.notransaksi = %s
            ORDER BY dt.nobaris ASC
        """, (notransaksi,))
        items = cur.fetchall()

        cur.execute("SELECT confvalue FROM tbl_conf WHERE confname = 'CMP_NAMA' LIMIT 1")
        conf_row = cur.fetchone()
        nama_toko = conf_row["confvalue"].strip() if (conf_row and conf_row.get("confvalue")) else "BANGKA MART"

        cur.close()
        conn.close()
        
        header = {
            "nama_toko": nama_toko,
            "notransaksi": hd["notransaksi"],
            "waktu": hd["waktu"],
            "kasir": hd["kasir"] or "KASIR",
            "dept_gdng": hd["dept_gdng"],
            "customer": hd["customer"],
            "totalitem": int(hd["totalitem"]),
            "subtotal": float(hd["subtotal"]),
            "potfaktur": float(hd["potfaktur"]),
            "pajak": float(hd["pajak"]),
            "biayalain": float(hd["biayalain"]),
            "totalakhir": float(hd["totalakhir"]),
            "jmltunai": float(hd["jmltunai"]),
            "jmldebit": float(hd["jmldebit"]),
            "jmlkk": float(hd["jmlkk"]),
            "jmlemoney": float(hd["jmlemoney"]),
            "jmldeposit": float(hd["jmldeposit"]),
            "jmlkredit": float(hd["jmlkredit"]),
            "kembalian": float(hd["kembalian"]),
            "carabayar": determine_cara_bayar(hd)
        }
        
        item_list = []
        for i in items:
            item_list.append({
                "nobaris": int(i["nobaris"]),
                "kodeitem": i["kodeitem"],
                "namaitem": i["namaitem"],
                "jumlah": float(i["jumlah"]),
                "satuan": i["satuan"],
                "harga": float(i["harga"]),
                "potongan": float(i["potongan"]),
                "total": float(i["total"])
            })
            
        return jsonify({
            "status": "success",
            "nama_toko": nama_toko,
            "header": header,
            "items": item_list
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/omset", methods=["GET"])
@app.route("/api/omset-hari-ini", methods=["GET"])
def get_omset():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Omset hari ini
        cur.execute("""
            SELECT COALESCE(SUM(totalakhir), 0) AS omset_hari_ini
            FROM tbl_ikhd
            WHERE tanggal::date = CURRENT_DATE
        """)
        omset_hari_ini = float(cur.fetchone()["omset_hari_ini"])

        # 2. Omset bulan ini
        cur.execute("""
            SELECT COALESCE(SUM(totalakhir), 0) AS omset_bulan_ini
            FROM tbl_ikhd
            WHERE EXTRACT(MONTH FROM tanggal) = EXTRACT(MONTH FROM CURRENT_DATE)
              AND EXTRACT(YEAR FROM tanggal) = EXTRACT(YEAR FROM CURRENT_DATE)
        """)
        omset_bulan_ini = float(cur.fetchone()["omset_bulan_ini"])

        # 3. Jumlah transaksi hari ini
        cur.execute("""
            SELECT COUNT(*) AS jumlah_transaksi
            FROM tbl_ikhd
            WHERE tanggal::date = CURRENT_DATE
        """)
        jumlah_transaksi = int(cur.fetchone()["jumlah_transaksi"])

        # 4. Data penjualan harian 7 hari terakhir
        cur.execute("""
            SELECT tanggal::date::text AS tanggal, COALESCE(SUM(totalakhir), 0) AS total
            FROM tbl_ikhd
            WHERE tanggal::date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY tanggal::date
            ORDER BY tanggal::date ASC
        """)
        daily_sales = []
        for r in cur.fetchall():
            raw_tgl = r["tanggal"]
            try:
                dt_obj = datetime.datetime.strptime(raw_tgl, "%Y-%m-%d")
                tgl_disp = dt_obj.strftime("%d/%m")
            except:
                tgl_disp = raw_tgl
            daily_sales.append({
                "tanggal": raw_tgl,
                "tanggal_display": tgl_disp,
                "total": float(r["total"])
            })

        # Top 5 Produk
        top_products = []

        cur.close()
        conn.close()

        now = get_wib_now()
        months_id = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        bulan_nama = months_id[now.month]
        bulan_display = f"{bulan_nama} {now.year}"
        tanggal_display = now.strftime("%d/%m/%y")

        return jsonify({
            "omset_hari_ini": omset_hari_ini,
            "omset_bulan_ini": omset_bulan_ini,
            "jumlah_transaksi_hari_ini": jumlah_transaksi,
            "tanggal": now.strftime("%Y-%m-%d"),
            "tanggal_display": tanggal_display,
            "bulan_display": bulan_display,
            "daily_sales": daily_sales,
            "top_products": top_products
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

if __name__ == "__main__":
    print(f"=====================================================")
    print(f"   iPos 4 Owner REST API Server (Database: {DB_DATABASE})")
    print(f"   Database: PostgreSQL 127.0.0.1:{DB_PORT}")
    print(f"   Akses Local: http://localhost:8000/api/omset")
    print(f"   Akses LAN:   http://192.168.100.9:8000/api/omset")
    print(f"=====================================================")
    app.run(host="0.0.0.0", port=8000, debug=False)
