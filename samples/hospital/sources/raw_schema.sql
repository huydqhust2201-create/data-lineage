-- Định nghĩa schema các bảng nguồn (raw layer) của hospital sample.
-- Các model dbt (stg_*, int_*, mart_*) là SELECT nên không mang kiểu cột;
-- kiểu + constraint chỉ khai được ở tầng raw này. Dùng cho tính năng
-- "column type + constraint" của Impact Analysis (Chủ đề 3).
--
-- Đây là schema tự dựng cho sample, KHÔNG phải introspect từ warehouse thật.

CREATE TABLE raw_patients (
    patient_id INTEGER NOT NULL PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20),
    insurance_provider VARCHAR(100)
);

CREATE TABLE raw_departments (
    department_id INTEGER NOT NULL PRIMARY KEY,
    department_name VARCHAR(120) NOT NULL
);

CREATE TABLE raw_doctors (
    doctor_id INTEGER NOT NULL PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    department_id INTEGER NOT NULL REFERENCES raw_departments (department_id)
);

CREATE TABLE raw_admissions (
    admission_id INTEGER NOT NULL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES raw_patients (patient_id),
    ward VARCHAR(60),
    admitted_at TIMESTAMP NOT NULL,
    discharged_at TIMESTAMP
);

CREATE TABLE raw_appointments (
    appointment_id INTEGER NOT NULL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES raw_patients (patient_id),
    doctor_id INTEGER NOT NULL REFERENCES raw_doctors (doctor_id),
    appointment_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE raw_invoices (
    invoice_id INTEGER NOT NULL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES raw_patients (patient_id),
    department_id INTEGER REFERENCES raw_departments (department_id),
    amount_billed NUMERIC(12, 2) NOT NULL,
    amount_paid NUMERIC(12, 2)
);

CREATE TABLE raw_lab_orders (
    order_id INTEGER NOT NULL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES raw_patients (patient_id)
);

CREATE TABLE raw_lab_results (
    result_id INTEGER NOT NULL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES raw_lab_orders (order_id),
    test_name VARCHAR(120) NOT NULL,
    result_value NUMERIC(12, 4),
    is_abnormal BOOLEAN NOT NULL
);
