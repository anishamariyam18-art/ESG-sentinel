import dotenv from 'dotenv';
import logger from './logger.js';

dotenv.config();

const REQUIRED_ENV_VARS = [
    'PORT',
    'NODE_ENV',
    'DB_HOST',
    'DB_PORT',
    'DB_NAME',
    'DB_USER',
    'DB_PASSWORD',
    'JWT_SECRET',
    'JWT_EXPIRES_IN',
    'FASTAPI_BASE_URL',
    'UPLOAD_PATH',
    'MAX_FILE_SIZE',
];

const validateEnvironment = () => {
    const missingVars = REQUIRED_ENV_VARS.filter((key) => {
        const value = process.env[key];
        return value === undefined || value === null || value.trim() === '';
    });

    if (missingVars.length > 0) {
        logger.error(
            `Missing required environment variables: ${missingVars.join(', ')}`
        );
        process.exit(1);
    }
};

validateEnvironment();

const config = Object.freeze({
    port: parseInt(process.env.PORT, 10),
    nodeEnv: process.env.NODE_ENV,

    db: Object.freeze({
        host: process.env.DB_HOST,
        port: parseInt(process.env.DB_PORT, 10),
        name: process.env.DB_NAME,
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
    }),

    jwt: Object.freeze({
        secret: process.env.JWT_SECRET,
        expiresIn: process.env.JWT_EXPIRES_IN,
    }),

    fastapi: Object.freeze({
        baseUrl: process.env.FASTAPI_BASE_URL,
    }),

    upload: Object.freeze({
        path: process.env.UPLOAD_PATH,
        maxFileSize: parseInt(process.env.MAX_FILE_SIZE, 10),
    }),
});

export default config;