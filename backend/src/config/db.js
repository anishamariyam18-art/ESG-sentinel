import pg from 'pg';
import config from './env.js';
import logger from './logger.js';

const { Pool } = pg;

const pool = new Pool({
    host: config.db.host,
    port: config.db.port,
    database: config.db.name,
    user: config.db.user,
    password: config.db.password,

    ssl: {
        rejectUnauthorized: false,
    },

    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 10000,
});

pool.on('error', (err) => {
    logger.error(
        'Unexpected error on idle PostgreSQL client',
        err
    );
});

const connect = async() => {
    try {
        const client = await pool.connect();

        logger.info(
            `Connected to PostgreSQL database "${config.db.name}"`
        );

        client.release();

        return true;
    } catch (err) {
        logger.error(
            'Failed to connect to PostgreSQL database',
            err
        );

        throw err;
    }
};

const query = async(text, params = []) => {
    try {
        const result = await pool.query(
            text,
            params
        );

        return result;
    } catch (err) {
        logger.error(
            `Database query failed: ${text}`,
            err
        );

        throw err;
    }
};

const close = async() => {
    try {
        await pool.end();

        logger.info(
            'PostgreSQL connection pool closed'
        );
    } catch (err) {
        logger.error(
            'Failed to close PostgreSQL connection pool',
            err
        );

        throw err;
    }
};

export {
    pool,
    connect,
    query,
    close,
};