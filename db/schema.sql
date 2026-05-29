-- SlideAtlas v1.0 DDL
-- 실행 방법 (EC2 Instance Connect 접속 후):
--
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/schema.sql
--
-- 또는 psql 접속 후 \i db/schema.sql
-- 멱등 실행 가능 (IF NOT EXISTS) — 이미 있는 테이블은 건드리지 않음

-- ─────────────────────────────────────────────
-- 1. subject_codes  (과목 코드 마스터)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subject_codes (
    code       VARCHAR(10)  PRIMARY KEY,  -- 'HST', 'PATH', 'PARA'
    name_ko    VARCHAR(50),               -- '조직학'
    name_en    VARCHAR(50),               -- 'Histology'
    created_at TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- 2. institutions  (구독 기관)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS institutions (
    id                 VARCHAR(20)  PRIMARY KEY,  -- 기관코드, 슬라이드 ID 앞부분과 동일
    name_ko            VARCHAR(100),
    name_en            VARCHAR(100),
    domain             VARCHAR(100),              -- 이메일 도메인 (자가인증용)
    subscription_plan  VARCHAR(20),               -- 'histology_base', 'pathology_addon' 등
    subscription_start DATE,
    subscription_end   DATE,
    max_users          INT,
    created_at         TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- 3. users  (학생 + 관리자)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL       PRIMARY KEY,
    institution_id  VARCHAR(20)  REFERENCES institutions(id),
    email           VARCHAR(200) UNIQUE NOT NULL,
    password_hash   VARCHAR(255),
    role            VARCHAR(20)  DEFAULT 'student',  -- 'student', 'institution_admin', 'super_admin'
    last_login      TIMESTAMP,
    session_token   VARCHAR(255),
    created_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_institution_id ON users(institution_id);
CREATE INDEX IF NOT EXISTS idx_users_email          ON users(email);

-- ─────────────────────────────────────────────
-- 4. slides  (WSI 슬라이드 메타데이터)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS slides (
    id                  VARCHAR(50)  PRIMARY KEY,   -- 'HS-HST-001'
    institution_id      VARCHAR(20),
    subject_code        VARCHAR(20),
    title_ko            VARCHAR(200),
    title_en            VARCHAR(200),
    description         TEXT,
    s3_key              VARCHAR(500),               -- COG TIFF S3 경로
    s3_minimap_key      VARCHAR(500),               -- minimap.png S3 경로
    s3_thumbnail_key    VARCHAR(500),               -- thumbnail.jpg S3 경로
    mpp                 FLOAT,                      -- μm/px, NULL 허용 (ready_no_mpp 상태)
    width               INT,
    height              INT,
    stain               VARCHAR(50),                -- 'H&E', 'PAS', 'Masson Trichrome'
    organ               VARCHAR(100),               -- 조직/장기 (소장, 간, 림프절 등)
    species             VARCHAR(50)  DEFAULT 'human',
    license_source      VARCHAR(100),               -- 'Happy Science', 'TCGA', '3DHISTECH'
    original_format     VARCHAR(20),                -- 'SVS', 'DCM', 'TIFF', 'NDPI', 'VSI'
    conversion_status   VARCHAR(20)  DEFAULT 'pending',
        -- pending / converting / qc_check / ready / ready_no_mpp / failed
    conversion_log      TEXT,
    qc_passed_at        TIMESTAMP,
    is_public           BOOLEAN      DEFAULT FALSE,
    knowledge_base      JSONB,                      -- AI 튜터용 {key_structures, exam_points, common_confusions}
    created_at          TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slides_institution_id    ON slides(institution_id);
CREATE INDEX IF NOT EXISTS idx_slides_conversion_status ON slides(conversion_status);
-- educational_qc_status 컬럼은 현재 v1.0 스키마에 미포함 → 추가 시 아래 주석 해제
-- CREATE INDEX IF NOT EXISTS idx_slides_educational_qc ON slides(educational_qc_status);

-- ─────────────────────────────────────────────
-- 5. plan_slide_access  (플랜별 접근 가능 과목)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plan_slide_access (
    plan         VARCHAR(20),
    subject_code VARCHAR(20),
    PRIMARY KEY (plan, subject_code)
);

-- ─────────────────────────────────────────────
-- 6. access_logs  (슬라이드 열람 로그)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS access_logs (
    id          SERIAL      PRIMARY KEY,
    user_id     INT         REFERENCES users(id),
    slide_id    VARCHAR(50) REFERENCES slides(id),
    accessed_at TIMESTAMP   DEFAULT NOW(),
    session_id  VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_access_logs_user_id     ON access_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_slide_id    ON access_logs(slide_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_accessed_at ON access_logs(accessed_at);

-- ─────────────────────────────────────────────
-- 7. courses  (강의 — 기관별 교수가 개설)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS courses (
    id                 SERIAL       PRIMARY KEY,
    institution_id     VARCHAR(20)  REFERENCES institutions(id),
    professor_user_id  INT          REFERENCES users(id),
    title              VARCHAR(200),
    semester           VARCHAR(20),  -- '2026-1', '2026-2'
    created_at         TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_courses_institution_id    ON courses(institution_id);
CREATE INDEX IF NOT EXISTS idx_courses_professor_user_id ON courses(professor_user_id);

-- ─────────────────────────────────────────────
-- 8. course_weeks  (강의 주차)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_weeks (
    id           SERIAL       PRIMARY KEY,
    course_id    INT          REFERENCES courses(id),
    week_number  INT,
    title        VARCHAR(200)
);

-- ─────────────────────────────────────────────
-- 9. course_week_slides  (주차별 슬라이드 배정)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_week_slides (
    course_week_id  INT          REFERENCES course_weeks(id),
    slide_id        VARCHAR(50)  REFERENCES slides(id),
    display_order   INT,
    PRIMARY KEY (course_week_id, slide_id)
);

-- ─────────────────────────────────────────────
-- 10. course_assistants  (강의 조교)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_assistants (
    course_id  INT  REFERENCES courses(id),
    user_id    INT  REFERENCES users(id),
    PRIMARY KEY (course_id, user_id)
);

-- ─────────────────────────────────────────────
-- 11. 기본 데이터 (과목 코드)
-- ─────────────────────────────────────────────
INSERT INTO subject_codes (code, name_ko, name_en) VALUES
    ('HST',   '조직학',   'Histology'),
    ('PATH',  '병리학',   'Pathology'),
    ('PARA',  '기생충학', 'Parasitology'),
    ('ANAT',  '해부학',   'Anatomy'),
    ('EMBRY', '발생학',   'Embryology')
ON CONFLICT (code) DO NOTHING;
