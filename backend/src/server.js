import config from './config/env.js';
import logger from './config/logger.js';
import { connect, close } from './config/db.js';
import app from './app.js';

let server;

const startServer = async() => {
    try {
        await connect();

        server = app.listen(config.port, () => {
            logger.info(`ESG Sentinel server running on port ${config.port} in ${config.nodeEnv} mode`);
        });
    } catch (err) {
        logger.error('Failed to start server', err);
        process.exit(1);
    }
};

const gracefulShutdown = async(signal) => {
    logger.info(`Received ${signal}. Starting graceful shutdown...`);

    if (server) {
        server.close(async() => {
            logger.info('HTTP server closed');

            try {
                await close();
                process.exit(0);
            } catch (err) {
                logger.error('Error during database shutdown', err);
                process.exit(1);
            }
        });
    } else {
        await close();
        process.exit(0);
    }
};

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

process.on('unhandledRejection', (reason) => {
    logger.error('Unhandled promise rejection', reason);
    process.exit(1);
});

process.on('uncaughtException', (err) => {
    logger.error('Uncaught exception', err);
    process.exit(1);
});

startServer();