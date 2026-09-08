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

        return (
            value === undefined ||
            value === null ||
            value.trim() === ''
        );
    });

    if (missingVars.length > 0) {
        logger.error(
            `Missing required environment variables: ${missingVars.join(', ')}`
        );

        process.exit(1);
    }
};

validateEnvironment();

const port = parseInt(process.env.PORT, 10);
const dbPort = parseInt(process.env.DB_PORT, 10);
const maxFileSize = parseInt(process.env.MAX_FILE_SIZE, 10);

if (Number.isNaN(port)) {
    logger.error('PORT must be a valid number');
    process.exit(1);
}

if (Number.isNaN(dbPort)) {
    logger.error('DB_PORT must be a valid number');
    process.exit(1);
}

if (Number.isNaN(maxFileSize)) {
    logger.error('MAX_FILE_SIZE must be a valid number');
    process.exit(1);
}

const config = Object.freeze({
    port,

    nodeEnv: process.env.NODE_ENV,

    db: Object.freeze({
        host: process.env.DB_HOST,
        port: dbPort,
        name: process.env.DB_NAME,
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
    }),

    jwt: Object.freeze({
        secret: process.env.JWT_SECRET,
        expiresIn: process.env.JWT_EXPIRES_IN,
    }),

    fastapi: Object.freeze({
        baseUrl: process.env.FASTAPI_BASE_URL.replace(/\/+$/, ''),
    }),

    upload: Object.freeze({
        path: process.env.UPLOAD_PATH,
        maxFileSize,
    }),
});

export default config;