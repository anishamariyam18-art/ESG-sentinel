import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import config from '../config/env.js';
import logger from '../config/logger.js';

import {
    createUser,
    findUserByEmail,
    findUserById,
    saveResetToken,
    findUserByResetToken,
    clearResetToken,
} from '../models/user.model.js';

const SALT_ROUNDS = 10;

const hashPassword = async(plainPassword) => {
    return bcrypt.hash(plainPassword, SALT_ROUNDS);
};

const comparePassword = async(plainPassword, hashedPassword) => {
    return bcrypt.compare(plainPassword, hashedPassword);
};

const generateToken = (user) => {
    return jwt.sign({
            id: user.id,
            email: user.email,
            role: user.role,
        },
        config.jwt.secret, {
            expiresIn: config.jwt.expiresIn,
        }
    );
};

const sanitizeUser = (user) => {
    const { password, reset_token, reset_token_expiry, ...safeUser } = user;
    return safeUser;
};

const registerUser = async({ name, email, password }) => {
    const existingUser = await findUserByEmail(email);

    if (existingUser) {
        const error = new Error('Email is already registered');
        error.statusCode = 409;
        throw error;
    }

    const hashedPassword = await hashPassword(password);

    const user = await createUser({
        name,
        email,
        password: hashedPassword,
        role: 'user',
    });

    return {
        user: sanitizeUser(user),
        token: generateToken(user),
    };
};

const loginUser = async({ email, password }) => {
    const user = await findUserByEmail(email);

    if (!user) {
        const error = new Error('Invalid email or password');
        error.statusCode = 401;
        throw error;
    }

    const valid = await comparePassword(password, user.password);

    if (!valid) {
        const error = new Error('Invalid email or password');
        error.statusCode = 401;
        throw error;
    }

    return {
        user: sanitizeUser(user),
        token: generateToken(user),
    };
};

const googleLoginUser = async({ email, name }) => {
    let user = await findUserByEmail(email);

    if (!user) {
        const randomPassword = crypto.randomBytes(20).toString('hex');

        const hashedPassword = await hashPassword(randomPassword);

        user = await createUser({
            name,
            email,
            password: hashedPassword,
            role: 'user',
        });

        logger.info(`Google user created: ${email}`);
    }

    return {
        user: sanitizeUser(user),
        token: generateToken(user),
    };
};

const forgotPasswordUser = async(email) => {
    const user = await findUserByEmail(email);

    if (!user) {
        const error = new Error('User not found');
        error.statusCode = 404;
        throw error;
    }

    const token = crypto.randomBytes(32).toString('hex');

    const expiry = new Date(Date.now() + 60 * 60 * 1000);

    await saveResetToken(user.id, token, expiry);

    logger.info(`Reset token generated for ${email}`);

    return token;
};

const resetPasswordUser = async(token, password) => {
    const user = await findUserByResetToken(token);

    if (!user) {
        const error = new Error('Invalid reset token');
        error.statusCode = 400;
        throw error;
    }

    if (new Date(user.reset_token_expiry) < new Date()) {
        const error = new Error('Reset token expired');
        error.statusCode = 400;
        throw error;
    }

    const hashedPassword = await hashPassword(password);

    await saveResetToken(user.id, null, null);

    const { query } = await
    import ('../config/db.js');

    await query(
        `UPDATE users
         SET password=$1,
             reset_token=NULL,
             reset_token_expiry=NULL,
             updated_at=CURRENT_TIMESTAMP
         WHERE id=$2`, [hashedPassword, user.id]
    );

    logger.info(`Password reset successful for ${user.email}`);
};

const getUserProfile = async(userId) => {
    const user = await findUserById(userId);

    if (!user) {
        const error = new Error('User not found');
        error.statusCode = 404;
        throw error;
    }

    return user;
};

export {
    hashPassword,
    comparePassword,
    generateToken,
    registerUser,
    loginUser,
    googleLoginUser,
    forgotPasswordUser,
    resetPasswordUser,
    getUserProfile,
};