WITH user_alarm_topics AS (
    -- CTE 1: Lấy thông tin Alarm và các Topic liên kết
    SELECT
        a.alarmId,
        a.userId,
        a.label AS alarm_label,
        t.topicId,
        t.topicName
    FROM "Alarm" a
    JOIN "AlarmTopicLink" atl ON a.alarmId = atl.alarmId
    JOIN "Topic" t ON atl.topicId = t.topicId
    WHERE a.missionType = 'QUIZ' AND a.isEnabled = true
),
user_question_history AS (
    -- CTE 2: Lấy lịch sử trả lời Quiz của user, tính thời gian phản hồi trung bình
    SELECT
        h.userId,
        h.questionId,
        h.isCorrect,
        h.timeToAnswerMs,
        h.answeredAt,
        q.ownerTopicId,
        q.prompt AS question_prompt
    FROM "History" h
    JOIN "Question" q ON h.questionId = q.questionId
    WHERE h.alarmHistoryId IS NOT NULL
),
quiz_performance_stats AS (
    -- CTE 3: Nhóm và tính toán thống kê hiệu suất theo User và Topic
    SELECT
        uqh.userId,
        uqh.ownerTopicId,
        COUNT(uqh.questionId) AS total_answered,
        SUM(CASE WHEN uqh.isCorrect = true THEN 1 ELSE 0 END) AS total_correct,
        AVG(uqh.timeToAnswerMs) AS avg_time_to_answer,
        MAX(uqh.answeredAt) AS last_answered_at
    FROM user_question_history uqh
    GROUP BY uqh.userId, uqh.ownerTopicId
),
ranked_topic_performance AS (
    -- CTE 4: Xếp hạng các Topic học tập của User dựa trên độ chính xác và tốc độ
    SELECT
        qps.userId,
        qps.ownerTopicId,
        qps.total_answered,
        qps.total_correct,
        qps.avg_time_to_answer,
        (CAST(qps.total_correct AS DOUBLE) / qps.total_answered) * 100 AS accuracy_percentage,
        ROW_NUMBER() OVER (
            PARTITION BY qps.userId
            ORDER BY (CAST(qps.total_correct AS DOUBLE) / qps.total_answered) DESC, qps.avg_time_to_answer ASC
        ) AS topic_rank
    FROM quiz_performance_stats qps
    WHERE qps.total_answered >= 5
),
user_progress_summary AS (
    -- CTE 5: Kết hợp thông tin tiến trình chi tiết của QuestionProgress và Elo Score
    SELECT
        qp.userId,
        qp.questionId,
        qp.correctStreak AS current_streak,
        qp.difficultyScore,
        ts.userEloScore,
        ts.topicId
    FROM "QuestionProgress" qp
    JOIN "TopicStats" ts ON qp.userId = ts.userId AND ts.topicId = qp.questionId
)
-- SELECT cuối cùng: Tổng hợp thông tin từ toàn bộ các CTE lồng nhau
SELECT
    u.username AS user_name,
    uat.alarm_label AS active_alarm,
    uat.topicName AS topic_name,
    rtp.total_answered AS answered_count,
    rtp.accuracy_percentage AS topic_accuracy,
    ups.current_streak AS question_streak,
    ups.difficultyScore AS question_difficulty,
    ups.userEloScore AS elo_rating
FROM user_progress_summary ups
JOIN ranked_topic_performance rtp ON ups.userId = rtp.userId AND ups.topicId = rtp.ownerTopicId
JOIN user_alarm_topics uat ON rtp.userId = uat.userId AND rtp.ownerTopicId = uat.topicId
JOIN "User" u ON ups.userId = u.userId
WHERE rtp.topic_rank <= 3
ORDER BY u.username ASC, rtp.topic_rank ASC;
