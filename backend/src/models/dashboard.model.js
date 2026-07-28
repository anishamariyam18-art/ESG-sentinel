import { query } from "../config/db.js";


// ===============================
// TOTAL USERS
// ===============================
const getTotalUsers = async() => {
    const result = await query(
        `SELECT COUNT(*)::int AS count 
         FROM users`
    );

    return result.rows[0].count;
};


// ===============================
// TOTAL REPORTS
// ===============================
const getTotalReports = async() => {
    const result = await query(
        `SELECT COUNT(*)::int AS count 
         FROM reports`
    );

    return result.rows[0].count;
};


// ===============================
// REPORT STATUS COUNT
// ===============================
const getReportsGroupedByStatus = async() => {
    const result = await query(
        `
        SELECT 
            status,
            COUNT(*)::int AS count
        FROM reports
        GROUP BY status
        `
    );

    return result.rows;
};


// ===============================
// AVERAGE TRUST SCORE
// ===============================
const getAverageTrustScore = async() => {
    const result = await query(
        `
        SELECT 
            AVG(overall_score)::numeric(5,2) AS average
        FROM trust_scores
        `
    );

    return result.rows[0].average;
};


// ===============================
// AVERAGE ESG SCORES
// ===============================
const getAverageEsgScores = async() => {

    const result = await query(
        `
        SELECT
            AVG(environment_score)::numeric(5,2) AS avg_environment,
            AVG(social_score)::numeric(5,2) AS avg_social,
            AVG(governance_score)::numeric(5,2) AS avg_governance
        FROM trust_scores
        `
    );

    return result.rows[0];
};


// ===============================
// GREENWASHING DISTRIBUTION
// ===============================
const getGreenwashingDistribution = async() => {

    const result = await query(
        `
        SELECT 
            risk_level,
            COUNT(*)::int AS count
        FROM greenwashing_results
        GROUP BY risk_level
        `
    );

    return result.rows;
};


// ===============================
// RECENT REPORTS
// ===============================
const getLatestReports = async(limit = 5) => {

    const result = await query(
        `
        SELECT 
            id,
            original_filename,
            status,
            uploaded_at
        FROM reports
        ORDER BY uploaded_at DESC
        LIMIT $1
        `, [limit]
    );

    return result.rows;
};



// =================================================
// HISTORY DATA
// ESG SCORE TREND FOR USER
// =================================================
const getHistoryData = async(userId) => {

    const result = await query(
        `
        SELECT
            DATE_TRUNC('month', r.uploaded_at) AS month,

            AVG(ts.overall_score)::numeric(5,2)
                AS trust_score,

            AVG(ts.environment_score)::numeric(5,2)
                AS environment_score,

            AVG(ts.social_score)::numeric(5,2)
                AS social_score,

            AVG(ts.governance_score)::numeric(5,2)
                AS governance_score

        FROM reports r

        JOIN trust_scores ts
        ON r.id = ts.report_id

        WHERE r.user_id = $1

        GROUP BY month

        ORDER BY month ASC
        `, [userId]
    );


    return result.rows;
};



// =================================================
// USER STATISTICS
// =================================================
const getStatisticsData = async(userId) => {

    const result = await query(
        `
        SELECT

        COUNT(DISTINCT r.id)::int
            AS total_reports,

        AVG(ts.overall_score)::numeric(5,2)
            AS average_score,

        MAX(ts.overall_score)::numeric(5,2)
            AS highest_score,

        MIN(ts.overall_score)::numeric(5,2)
            AS lowest_score


        FROM reports r

        LEFT JOIN trust_scores ts
        ON r.id = ts.report_id

        WHERE r.user_id = $1
        `, [userId]
    );


    return result.rows[0];
};




// =================================================
// COMPANY ESG HISTORY
// =================================================
const getCompanyHistoryData = async(company) => {


    const result = await query(
        `
        SELECT

            EXTRACT(YEAR FROM r.uploaded_at)::int 
                AS year,


            AVG(ts.environment_score)::numeric(5,2)
                AS environment_score,


            AVG(ts.social_score)::numeric(5,2)
                AS social_score,


            AVG(ts.governance_score)::numeric(5,2)
                AS governance_score,


            AVG(ts.overall_score)::numeric(5,2)
                AS overall_score


        FROM reports r


        JOIN trust_scores ts
        ON r.id = ts.report_id


        WHERE r.company_name = $1


        GROUP BY year


        ORDER BY year ASC
        `, [company]
    );


    return result.rows;
};






// =================================================
// YEAR COMPARISON
// =================================================
const compareYearData = async(year) => {


    const result = await query(
        `
        SELECT

            r.company_name,


            AVG(ts.overall_score)::numeric(5,2)
                AS average_score,


            AVG(ts.environment_score)::numeric(5,2)
                AS environment_score,


            AVG(ts.social_score)::numeric(5,2)
                AS social_score,


            AVG(ts.governance_score)::numeric(5,2)
                AS governance_score



        FROM reports r


        JOIN trust_scores ts
        ON r.id = ts.report_id



        WHERE EXTRACT(YEAR FROM r.uploaded_at) = $1



        GROUP BY r.company_name


        ORDER BY average_score DESC
        `, [year]
    );


    return result.rows;
};





export {
    getTotalUsers,
    getTotalReports,
    getReportsGroupedByStatus,
    getAverageTrustScore,
    getAverageEsgScores,
    getGreenwashingDistribution,
    getLatestReports,

    getHistoryData,
    getStatisticsData,
    getCompanyHistoryData,
    compareYearData,
};