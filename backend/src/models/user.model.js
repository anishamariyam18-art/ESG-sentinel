import { query } from '../config/db.js';

const createUser = async({ name, email, password, role = 'user' }) => {
    const result = await query(
        `INSERT INTO users
        (name, email, password, role)
        VALUES ($1, $2, $3, $4)
        RETURNING
            id,
            name,
            email,
            role,
            created_at,
            updated_at`, [name, email, password, role]
    );

    return result.rows[0];
};

const findUserByEmail = async(email) => {
    const result = await query(
        `SELECT
            id,
            name,
            email,
            password,
            role,
            reset_token,
            reset_token_expiry,
            created_at,
            updated_at
        FROM users
        WHERE email = $1`, [email]
    );

    return result.rows[0] || null;
};

const findUserById = async(id) => {
    const result = await query(
        `SELECT
            id,
            name,
            email,
            role,
            created_at,
            updated_at
        FROM users
        WHERE id = $1`, [id]
    );

    return result.rows[0] || null;
};

const updateUser = async(id, { name, email }) => {
    const result = await query(
        `UPDATE users
        SET
            name = COALESCE($1, name),
            email = COALESCE($2, email),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $3
        RETURNING
            id,
            name,
            email,
            role,
            created_at,
            updated_at`, [name, email, id]
    );

    return result.rows[0] || null;
};

const deleteUser = async(id) => {
    const result = await query(
        `DELETE FROM users
        WHERE id = $1
        RETURNING id`, [id]
    );

    return result.rows[0] || null;
};

const saveResetToken = async(userId, token, expiry) => {
    await query(
        `UPDATE users
        SET
            reset_token = $1,
            reset_token_expiry = $2,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $3`, [token, expiry, userId]
    );
};

const findUserByResetToken = async(token) => {
    const result = await query(
        `SELECT
            id,
            name,
            email,
            password,
            role,
            reset_token,
            reset_token_expiry
        FROM users
        WHERE reset_token = $1`, [token]
    );

    return result.rows[0] || null;
};

const clearResetToken = async(userId) => {
    await query(
        `UPDATE users
        SET
            reset_token = NULL,
            reset_token_expiry = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1`, [userId]
    );
};

export {
    createUser,
    findUserByEmail,
    findUserById,
    updateUser,
    deleteUser,
    saveResetToken,
    findUserByResetToken,
    clearResetToken,
};