const LOG_LEVELS = Object.freeze({
    INFO: 'INFO',
    WARN: 'WARN',
    ERROR: 'ERROR',
    DEBUG: 'DEBUG',
});

const isDebugEnabled = () => process.env.NODE_ENV !== 'production';

const buildLogEntry = (level, message) => {
    const timestamp = new Date().toISOString();
    return `[${timestamp}] [${level}] ${message}`;
};

const info = (message) => {
    console.log(buildLogEntry(LOG_LEVELS.INFO, message));
};

const warn = (message) => {
    console.warn(buildLogEntry(LOG_LEVELS.WARN, message));
};

const error = (message, err) => {
    const baseMessage = buildLogEntry(LOG_LEVELS.ERROR, message);
    if (err instanceof Error) {
        console.error(baseMessage);
        console.error(err.stack);
    } else if (err !== undefined) {
        console.error(baseMessage, err);
    } else {
        console.error(baseMessage);
    }
};

const debug = (message) => {
    if (!isDebugEnabled()) {
        return;
    }
    console.debug(buildLogEntry(LOG_LEVELS.DEBUG, message));
};

const logger = {
    info,
    warn,
    error,
    debug,
};

export default logger;