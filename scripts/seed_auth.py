from src.services import auth_service, database_service, user_service

DEFAULT_USERS = (
    ("engineer@example.com", "Engineer", "password123"),
    ("viewer@example.com", "Viewer", "password123"),
)


def main() -> None:
    seeded = []
    for email, display_name, password in DEFAULT_USERS:
        existing = user_service.get_by_email_with_credentials(email)
        if existing is None:
            user = user_service.register(email, display_name, auth_service.hash_password(password))
            assert user is not None
        else:
            user = user_service.ensure_user(email, display_name)  # idempotent re-run, giữ display_name mới nhất
            if existing.password_hash is None:  # user tạo từ trước tính năng auth, chưa có mật khẩu
                user = user_service.set_password(user.id, auth_service.hash_password(password))
        seeded.append(user)
        print(f"seeded user id={user.id} email={user.email} password={password}")

    owner = seeded[0]
    database = database_service.get_database_for_owner_and_name(owner.id, "default")
    if database is None:
        database = database_service.create_database(owner.id, "default")
    assert database is not None
    print(f"seeded database id={database.id} owner_id={owner.id}")


if __name__ == "__main__":
    main()
