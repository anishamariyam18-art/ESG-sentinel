import { query } from '../config/db.js';

const createReport = async({
    userId,
    company,
    reportYear,
    originalFilename,
    storedFilename,
    filePath,
    fileSize,
}) => {
    const result = await query(
        `INSERT INTO reports (
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'uploaded')
        RETURNING
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at`, [
            userId,
            company,
            reportYear,
            originalFilename,
            storedFilename,
            filePath,
            fileSize,
        ]
    );

    return result.rows[0];
};


const findReportById = async(id) => {
    const result = await query(
        `SELECT
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at
        FROM reports
        WHERE id = $1`, [id]
    );

    return result.rows[0] || null;
};


const findReportsByUserId = async(
    userId, { limit = 20, offset = 0 } = {}
) => {
    const result = await query(
        `SELECT
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at
        FROM reports
        WHERE user_id = $1
        ORDER BY uploaded_at DESC
        LIMIT $2 OFFSET $3`, [userId, limit, offset]
    );

    return result.rows;
};


const getAllReports = async({ limit = 20, offset = 0 } = {}) => {
    const result = await query(
        `SELECT
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at
        FROM reports
        ORDER BY uploaded_at DESC
        LIMIT $1 OFFSET $2`, [limit, offset]
    );

    return result.rows;
};


const updateReportStatus = async(id, status) => {
    const result = await query(
        `UPDATE reports
        SET
            status = $1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        RETURNING
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at`, [status, id]
    );

    return result.rows[0] || null;
};


const updateReportDetails = async(
    id, {
        originalFilename,
        filePath,
        fileSize,
    }
) => {
    const result = await query(
        `UPDATE reports
        SET
            original_filename = COALESCE($1, original_filename),
            file_path = COALESCE($2, file_path),
            file_size = COALESCE($3, file_size),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $4
        RETURNING
            id,
            user_id,
            company,
            report_year,
            original_filename,
            stored_filename,
            file_path,
            file_size,
            status,
            uploaded_at,
            created_at,
            updated_at`, [
            originalFilename,
            filePath,
            fileSize,
            id,
        ]
    );

    return result.rows[0] || null;
};


const deleteReport = async(id) => {
    const result = await query(
        `DELETE FROM reports
        WHERE id = $1
        RETURNING id`, [id]
    );

    return result.rows[0] || null;
};


const countReports = async(userId = null) => {
    const result = userId ?
        await query(
            `SELECT COUNT(*)::int AS count
            FROM reports
            WHERE user_id = $1`, [userId]
        ) :
        await query(
            `SELECT COUNT(*)::int AS count
            FROM reports`
        );

    return result.rows[0].count;
};


export {
    createReport,
    findReportById,
    findReportsByUserId,
    getAllReports,
    updateReportStatus,
    updateReportDetails,
    deleteReport,
    countReports,
};