"""造 6 个演示库（MySQL 3 个 + PostgreSQL 3 个），汽车 4S 店业务。"""

import random
import datetime as dt

import pymysql
import psycopg2

random.seed(20261108)

# ── 基础数据 ──────────────────────────────────────────
SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
GIVEN = ["伟", "芳", "娜", "敏", "静", "强", "磊", "洋", "勇", "艳", "杰", "涛", "明", "超", "秀英", "建国", "晓东", "梦琪"]

DEPTS = [
    ("销售部", "负责整车销售"),
    ("维修部", "负责车辆维修保养"),
    ("财务部", "负责资金与账务"),
    ("采购部", "负责配件与整车采购"),
    ("管理部", "负责审批与管理"),
]

ROLES = {
    "销售部": ["销售顾问", "销售经理"],
    "维修部": ["维修技师", "维修顾问", "维修经理"],
    "财务部": ["会计", "出纳", "财务经理"],
    "采购部": ["采购员", "采购经理"],
    "管理部": ["总经理"],
}

MODELS = [
    ("大众", "朗逸", "轿车", 129800, 98000),
    ("大众", "途观L", "SUV", 219800, 175000),
    ("丰田", "卡罗拉", "轿车", 119800, 91000),
    ("丰田", "汉兰达", "SUV", 269800, 218000),
    ("本田", "雅阁", "轿车", 179800, 142000),
    ("比亚迪", "汉EV", "新能源", 219800, 178000),
    ("特斯拉", "Model 3", "新能源", 235500, 198000),
    ("奥迪", "A4L", "轿车", 359800, 298000),
]

COLORS = ["珍珠白", "曜石黑", "星空灰", "海云蓝", "赤焰红", "香槟金"]
LOCATIONS = ["A区-01", "A区-02", "B区-01", "B区-02", "C区-01", "展厅"]

PART_CATS = [
    ("机油", "保养", 268), ("机油滤清器", "保养", 65), ("空气滤清器", "保养", 88),
    ("刹车片", "制动", 420), ("刹车盘", "制动", 780), ("火花塞", "点火", 95),
    ("蓄电池", "电气", 680), ("雨刮片", "外观", 120), ("轮胎", "行走", 850),
    ("减震器", "悬挂", 960), ("空调滤芯", "保养", 110), ("变速箱油", "保养", 320),
]

TOOLS = [
    ("举升机", "设备"), ("四轮定位仪", "设备"), ("诊断电脑", "仪器"),
    ("气动扳手", "手动工具"), ("扭力扳手", "手动工具"), ("千斤顶", "手动工具"),
    ("内窥镜", "仪器"), ("压力表", "仪器"), ("电焊机", "设备"), ("喷漆房", "设备"),
]

SYMPTOMS = [
    "发动机异响", "刹车偏软", "空调不制冷", "启动困难", "油耗异常",
    "方向跑偏", "车灯不亮", "变速箱顿挫", "轮胎漏气", "仪表报警",
]


def name():
    return random.choice(SURNAMES) + random.choice(GIVEN)


def phone():
    return "1" + random.choice("35789") + "".join(random.choice("0123456789") for _ in range(9))


def d(days_ago_max=900):
    return dt.date.today() - dt.timedelta(days=random.randint(1, days_ago_max))


def vin(i):
    return f"LSV{random.randint(10000000, 99999999)}{i:04d}"


# ── MySQL ────────────────────────────────────────────
def mysql_conn(db=None):
    return pymysql.connect(
        host="127.0.0.1", port=3306, user="wren", password="wren123",
        database=db, charset="utf8mb4", autocommit=True,
    )


def build_mysql():
    # 建库
    c = mysql_conn()
    cur = c.cursor()
    for db in ("autostaff", "autosales", "autofinance"):
        cur.execute(f"DROP DATABASE IF EXISTS {db}")
        cur.execute(f"CREATE DATABASE {db} CHARACTER SET utf8mb4")
    c.close()

    # ---- autostaff ----
    c = mysql_conn("autostaff")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE departments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            description VARCHAR(200) NOT NULL DEFAULT ''
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE employees (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            dept_id INT NOT NULL,
            role VARCHAR(50) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            hire_date DATE NOT NULL,
            salary DECIMAL(10,2) NOT NULL,
            manager_id INT NULL,
            INDEX idx_dept (dept_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.executemany("INSERT INTO departments (name, description) VALUES (%s,%s)", DEPTS)

    emps = []
    for dept_id, (dname, _) in enumerate(DEPTS, start=1):
        for role in ROLES[dname]:
            for _ in range(3 if role.endswith("经理") else 6):
                emps.append([name(), dept_id, role, phone(), d(2000), 0, None])

    # 经理：每个部门第一个经理
    managers = {}
    for e in emps:
        if e[2].endswith("经理") and e[1] not in managers:
            managers[e[1]] = None

    cur.executemany(
        "INSERT INTO employees (name,dept_id,role,phone,hire_date,salary,manager_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        [[e[0], e[1], e[2], e[3], e[4], 0, None] for e in emps],
    )
    cur.execute("SELECT id, dept_id, role FROM employees")
    rows = cur.fetchall()
    for eid, dept_id, role in rows:
        if role.endswith("经理"):
            managers.setdefault(dept_id, eid)
    for eid, dept_id, role in rows:
        base = 6000 if "技师" in role or "顾问" in role else 7000
        if "经理" in role:
            base = 15000
        if "总经理" in role:
            base = 25000
        sal = base + random.randint(0, 3000)
        mgr = managers.get(dept_id)
        cur.execute(
            "UPDATE employees SET salary=%s, manager_id=%s WHERE id=%s",
            (sal, None if eid == mgr else mgr, eid),
        )
    c.close()

    # ---- autosales ----
    c = mysql_conn("autosales")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE customers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            city VARCHAR(50) NOT NULL,
            created_at DATE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE sales_orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_no VARCHAR(30) NOT NULL,
            customer_id INT NOT NULL,
            sales_id INT NOT NULL,
            manager_id INT NOT NULL,
            order_date DATE NOT NULL,
            total_amount DECIMAL(12,2) NOT NULL,
            status VARCHAR(20) NOT NULL,
            INDEX idx_cust (customer_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE sales_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            vin VARCHAR(30) NOT NULL,
            brand VARCHAR(30) NOT NULL,
            model VARCHAR(50) NOT NULL,
            price DECIMAL(12,2) NOT NULL,
            INDEX idx_order (order_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cities = ["上海", "北京", "杭州", "苏州", "南京", "广州", "成都", "武汉"]
    cur.executemany(
        "INSERT INTO customers (name,phone,city,created_at) VALUES (%s,%s,%s,%s)",
        [[name(), phone(), random.choice(cities), d(800)] for _ in range(40)],
    )
    cur.execute("SELECT id FROM autostaff.employees WHERE role LIKE '%销售%'")
    sellers = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT id FROM autostaff.employees WHERE role LIKE '%经理%'")
    mgrs = [r[0] for r in cur.fetchall()]

    orders = []
    for i in range(50):
        orders.append([
            f"SO{2025000 + i}", random.randint(1, 40), random.choice(sellers),
            random.choice(mgrs), d(600), 0, random.choice(["已交付", "已交付", "已交付", "已取消"]),
        ])
    cur.executemany(
        "INSERT INTO sales_orders (order_no,customer_id,sales_id,manager_id,order_date,total_amount,status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        orders,
    )

    items, vin_i = [], 0
    for oid in range(1, 51):
        brand, model, _category, msrp, cost = random.choice(MODELS)
        for _ in range(random.randint(1, 2)):
            vin_i += 1
            price = msrp - random.randint(0, 15000)
            items.append([oid, vin(vin_i), brand, model, price])
    cur.executemany(
        "INSERT INTO sales_items (order_id,vin,brand,model,price) VALUES (%s,%s,%s,%s,%s)",
        items,
    )
    cur.execute("""
        UPDATE sales_orders o
        SET total_amount = (SELECT COALESCE(SUM(price),0) FROM sales_items i WHERE i.order_id=o.id)
    """)
    c.close()

    # ---- autofinance ----
    c = mysql_conn("autofinance")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE payroll (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            month CHAR(7) NOT NULL,
            base DECIMAL(10,2) NOT NULL,
            bonus DECIMAL(10,2) NOT NULL DEFAULT 0,
            deduction DECIMAL(10,2) NOT NULL DEFAULT 0,
            net DECIMAL(10,2) NOT NULL,
            approver_id INT NOT NULL,
            paid_at DATE NOT NULL,
            INDEX idx_emp (employee_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE expense_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            dept VARCHAR(50) NOT NULL,
            purpose VARCHAR(200) NOT NULL,
            amount DECIMAL(12,2) NOT NULL,
            requester_id INT NOT NULL,
            approver_id INT NOT NULL,
            status VARCHAR(20) NOT NULL,
            requested_at DATE NOT NULL,
            approved_at DATE NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE accounts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            balance DECIMAL(14,2) NOT NULL,
            updated_at DATE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    c2 = mysql_conn("autostaff")
    cur2 = c2.cursor()
    cur2.execute("SELECT id, salary FROM employees")
    emps = cur2.fetchall()
    c2.close()
    pay = []
    today = dt.date.today()
    for m in range(6):
        y, mo = today.year, today.month - m
        while mo <= 0:
            mo += 12
            y -= 1
        month = f"{y}-{mo:02d}"
        for eid, salary in emps:
            base = float(salary)
            bonus = round(random.uniform(0, 3000), 2)
            ded = round(random.uniform(0, 800), 2)
            pay.append([eid, month, base, bonus, ded, round(base + bonus - ded, 2),
                        random.choice(mgrs), dt.date(y, mo, 28)])
    cur.executemany(
        "INSERT INTO payroll (employee_id,month,base,bonus,deduction,net,approver_id,paid_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        pay,
    )

    purposes = ["采购配件", "广告投放", "门店装修", "展会费用", "员工培训", "车辆运输", "水电物业"]
    exp = []
    for _ in range(25):
        req = d(300)
        ok = random.choice([True, True, True, False])
        exp.append([
            random.choice([x[0] for x in DEPTS]), random.choice(purposes),
            round(random.uniform(3000, 200000), 2), random.choice(sellers),
            random.choice(mgrs), "已批准" if ok else "待审批", req,
            req + dt.timedelta(days=random.randint(1, 10)) if ok else None,
        ])
    cur.executemany(
        "INSERT INTO expense_requests (dept,purpose,amount,requester_id,approver_id,status,requested_at,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        exp,
    )
    cur.executemany(
        "INSERT INTO accounts (name,balance,updated_at) VALUES (%s,%s,%s)",
        [["基本户", 3850000.00, today], ["一般户", 1250000.00, today], ["备用金", 86000.00, today]],
    )
    c.close()


# ── PostgreSQL ───────────────────────────────────────
def pg_conn(db):
    return psycopg2.connect(
        host="127.0.0.1", port=5432, dbname=db, user="wren", password="wren123"
    )


def build_pg():
    import os
    import subprocess

    if os.getenv("SKIP_DB_CREATE") != "1":
        for db in ("autowarehouse", "autoparts", "autorepair"):
            subprocess.run(
                ["sudo", "-n", "-u", "postgres", "psql", "-q", "-c",
                 f"DROP DATABASE IF EXISTS {db};"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["sudo", "-n", "-u", "postgres", "psql", "-q", "-c",
                 f"CREATE DATABASE {db} OWNER wren;"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    # ---- autowarehouse ----
    c = pg_conn("autowarehouse")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE models (
            id serial PRIMARY KEY,
            brand text NOT NULL,
            model_name text NOT NULL,
            category text NOT NULL,
            msrp numeric(12,2) NOT NULL,
            cost numeric(12,2) NOT NULL
        )""")
    cur.execute("""
        CREATE TABLE vehicles (
            id serial PRIMARY KEY,
            vin text NOT NULL,
            model_id int NOT NULL,
            color text NOT NULL,
            produced_at date NOT NULL,
            location text NOT NULL,
            status text NOT NULL,
            cost numeric(12,2) NOT NULL
        )""")
    cur.execute("""
        CREATE TABLE stock_moves (
            id serial PRIMARY KEY,
            vin text NOT NULL,
            from_loc text NOT NULL,
            to_loc text NOT NULL,
            moved_at date NOT NULL,
            operator_id int NOT NULL
        )""")
    cur.executemany(
        "INSERT INTO models (brand,model_name,category,msrp,cost) VALUES (%s,%s,%s,%s,%s)",
        MODELS,
    )
    vs = []
    for i in range(1, 41):
        mid = random.randint(1, len(MODELS))
        vs.append([vin(i), mid, random.choice(COLORS), d(500),
                   random.choice(LOCATIONS),
                   random.choice(["在库", "在库", "在库", "已出库"]),
                   MODELS[mid - 1][4]])
    cur.executemany(
        "INSERT INTO vehicles (vin,model_id,color,produced_at,location,status,cost) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        vs,
    )
    cur.executemany(
        "INSERT INTO stock_moves (vin,from_loc,to_loc,moved_at,operator_id) VALUES (%s,%s,%s,%s,%s)",
        [[random.choice(vs)[0], random.choice(LOCATIONS), random.choice(LOCATIONS), d(300),
          random.randint(1, 30)] for _ in range(40)],
    )
    c.commit()
    c.close()

    # ---- autoparts ----
    c = pg_conn("autoparts")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE parts (
            id serial PRIMARY KEY,
            sku text NOT NULL,
            name text NOT NULL,
            category text NOT NULL,
            unit_price numeric(10,2) NOT NULL,
            stock_qty int NOT NULL,
            reorder_level int NOT NULL
        )""")
    cur.execute("""
        CREATE TABLE tools (
            id serial PRIMARY KEY,
            code text NOT NULL,
            name text NOT NULL,
            kind text NOT NULL,
            status text NOT NULL,
            purchased_at date NOT NULL
        )""")
    cur.execute("""
        CREATE TABLE part_usage (
            id serial PRIMARY KEY,
            part_id int NOT NULL,
            repair_order_id int NOT NULL,
            qty int NOT NULL,
            used_at date NOT NULL,
            operator_id int NOT NULL
        )""")
    ps = []
    for i, (nm, cat, price) in enumerate(PART_CATS * 2, start=1):
        ps.append([f"SKU{i:04d}", nm, cat, price, random.randint(0, 120),
                   random.randint(10, 30)])
    cur.executemany(
        "INSERT INTO parts (sku,name,category,unit_price,stock_qty,reorder_level) VALUES (%s,%s,%s,%s,%s,%s)",
        ps,
    )
    cur.executemany(
        "INSERT INTO tools (code,name,kind,status,purchased_at) VALUES (%s,%s,%s,%s,%s)",
        [[f"T{i:03d}", n, k, random.choice(["可用", "可用", "维修中", "报废"]), d(1200)]
         for i, (n, k) in enumerate(TOOLS, start=1)],
    )
    cur.executemany(
        "INSERT INTO part_usage (part_id,repair_order_id,qty,used_at,operator_id) VALUES (%s,%s,%s,%s,%s)",
        [[random.randint(1, len(ps)), random.randint(1, 35), random.randint(1, 4), d(200),
          random.randint(1, 30)] for _ in range(60)],
    )
    c.commit()
    c.close()

    # ---- autorepair ----
    c = pg_conn("autorepair")
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE repair_orders (
            id serial PRIMARY KEY,
            order_no text NOT NULL,
            vin text NOT NULL,
            customer_name text NOT NULL,
            customer_phone text NOT NULL,
            advisor_id int NOT NULL,
            technician_id int NOT NULL,
            manager_id int NOT NULL,
            symptom text NOT NULL,
            status text NOT NULL,
            opened_at date NOT NULL,
            closed_at date,
            labor_cost numeric(10,2) NOT NULL DEFAULT 0,
            parts_cost numeric(10,2) NOT NULL DEFAULT 0
        )""")
    cur.execute("""
        CREATE TABLE repair_items (
            id serial PRIMARY KEY,
            repair_order_id int NOT NULL,
            description text NOT NULL,
            hours numeric(5,1) NOT NULL,
            cost numeric(10,2) NOT NULL
        )""")
    # 用 MySQL 里的 VIN
    c2 = pg_conn("autowarehouse")
    cur2 = c2.cursor()
    cur2.execute("SELECT vin FROM vehicles")
    vins = [r[0] for r in cur2.fetchall()]
    c2.close()

    ros = []
    for i in range(35):
        opened = d(400)
        done = random.choice([True, True, True, False])
        ros.append([
            f"RO{2025000 + i}", random.choice(vins), name(), phone(),
            random.randint(1, 30), random.randint(1, 30), random.randint(1, 30),
            random.choice(SYMPTOMS),
            "已完工" if done else "进行中", opened,
            opened + dt.timedelta(days=random.randint(1, 7)) if done else None,
            round(random.uniform(200, 3000), 2), 0,
        ])
    cur.executemany(
        """INSERT INTO repair_orders
           (order_no,vin,customer_name,customer_phone,advisor_id,technician_id,manager_id,
            symptom,status,opened_at,closed_at,labor_cost,parts_cost)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        ros,
    )
    cur.executemany(
        "INSERT INTO repair_items (repair_order_id,description,hours,cost) VALUES (%s,%s,%s,%s)",
        [[random.randint(1, 35), random.choice(SYMPTOMS) + "处理",
          round(random.uniform(0.5, 6), 1), round(random.uniform(100, 2500), 2)]
         for _ in range(70)],
    )
    cur.execute("""
        UPDATE repair_orders o
        SET parts_cost = COALESCE((SELECT SUM(cost) FROM repair_items i WHERE i.repair_order_id=o.id), 0)
    """)
    c.commit()
    c.close()


def summary():
    c = mysql_conn()
    cur = c.cursor()
    print("  ── MySQL ──")
    for db in ("autostaff", "autosales", "autofinance"):
        cur.execute(
            "SELECT table_name, table_rows FROM information_schema.tables "
            "WHERE table_schema=%s ORDER BY table_name", (db,)
        )
        for t, n in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM {db}.{t}")
            print(f"    {db}.{t:18} {cur.fetchone()[0]:>4} 行")
    c.close()

    print("  ── PostgreSQL ──")
    for db in ("autowarehouse", "autoparts", "autorepair"):
        c = pg_conn(db)
        cur = c.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
        for (t,) in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"    {db}.{t:18} {cur.fetchone()[0]:>4} 行")
        c.close()


if __name__ == "__main__":
    print("建 MySQL 库…")
    build_mysql()
    print("建 PostgreSQL 库…")
    build_pg()
    print("完成：\n")
    summary()
