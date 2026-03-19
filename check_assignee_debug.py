import sqlite3


def main():
    conn = sqlite3.connect("instance/badcase_doctor.db")
    cur = conn.cursor()

    print("== users sample (first 30) ==")
    for row in cur.execute("select id,name,email,is_verified from user order by id limit 30"):
        print(row)

    print("\n== users where name like '%33%' ==")
    for row in cur.execute("select id,name,email,is_verified from user where name='33' or name like '%33%' limit 50"):
        print(row)

    print("\n== user id=33 ==")
    for row in cur.execute("select id,name,email,is_verified from user where id=33"):
        print(row)

    print("\n== test_case latest 15 (id,title,assignee_id,project_id,plan_id) ==")
    for row in cur.execute("select id,title,assignee_id,project_id,plan_id from test_case order by id desc limit 15"):
        print(row)


if __name__ == "__main__":
    main()

