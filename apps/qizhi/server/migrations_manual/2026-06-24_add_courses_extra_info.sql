-- 手动迁移：给 courses 表新增 extra_info(JSONB) 列
-- 用途：承载课程展示扩展字段
--   grade(string) 授课对象年级 / category(string) 课程类别 / credits(number) 学分 /
--   major(string) 授课对象专业 / offline_hours_ratio(number) 线下学时占比 /
--   offline_score_ratio(number) 线下成绩占比
--
-- 说明：
-- 1. 本项目未使用 Alembic，采用 server/infra/db/database.py 中的 _STARTUP_MIGRATIONS
--    幂等启动迁移机制。同一条 ALTER 已加入该列表，后端正常重启即会自动执行。
-- 2. 本文件是给"手动执行"准备的等价 SQL（幂等，可重复执行），与启动迁移二选一即可。
--
-- 执行（在 Postgres 上以应用同库账号运行）：
--   psql "<DATABASE_URL>" -f 2026-06-24_add_courses_extra_info.sql

ALTER TABLE courses ADD COLUMN IF NOT EXISTS extra_info JSONB;

-- ============================================================
-- 回滚（仅在需要撤销时执行）：
-- ALTER TABLE courses DROP COLUMN IF EXISTS extra_info;
-- ============================================================
