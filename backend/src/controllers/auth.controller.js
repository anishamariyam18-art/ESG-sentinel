import {
    registerUser,
    loginUser,
    getUserProfile,
    googleLoginUser,
    forgotPasswordUser,
    resetPasswordUser,
} from '../services/auth.service.js';

const register = async(req, res, next) => {
    try {
        const { name, email, password } = req.body;

        if (!name || !email || !password) {
            const error = new Error('Name, email, and password are required');
            error.statusCode = 400;
            throw error;
        }

        const { user, token } = await registerUser({
            name,
            email,
            password,
        });

        res.status(201).json({
            success: true,
            message: 'User registered successfully',
            data: { user, token },
        });
    } catch (error) {
        next(error);
    }
};

const login = async(req, res, next) => {
    try {
        const { email, password } = req.body;

        if (!email || !password) {
            const error = new Error('Email and password are required');
            error.statusCode = 400;
            throw error;
        }

        const { user, token } = await loginUser({
            email,
            password,
        });

        res.status(200).json({
            success: true,
            message: 'Login successful',
            data: { user, token },
        });
    } catch (error) {
        next(error);
    }
};

const profile = async(req, res, next) => {
    try {
        const userId = req.user.id;

        const user = await getUserProfile(userId);

        res.status(200).json({
            success: true,
            message: 'Profile retrieved successfully',
            data: { user },
        });
    } catch (error) {
        next(error);
    }
};

const googleLogin = async(req, res, next) => {
    try {
        const { email, name } = req.body;

        if (!email || !name) {
            const error = new Error('Email and name are required');
            error.statusCode = 400;
            throw error;
        }

        const { user, token } = await googleLoginUser({
            email,
            name,
        });

        res.status(200).json({
            success: true,
            message: 'Google login successful',
            data: { user, token },
        });
    } catch (error) {
        next(error);
    }
};

const forgotPassword = async(req, res, next) => {
    try {
        const { email } = req.body;

        if (!email) {
            const error = new Error('Email is required');
            error.statusCode = 400;
            throw error;
        }

        await forgotPasswordUser(email);

        res.status(200).json({
            success: true,
            message: 'Password reset link generated successfully',
        });
    } catch (error) {
        next(error);
    }
};

const resetPassword = async(req, res, next) => {
    try {
        const { token, password } = req.body;

        if (!token || !password) {
            const error = new Error('Token and password are required');
            error.statusCode = 400;
            throw error;
        }

        await resetPasswordUser(token, password);

        res.status(200).json({
            success: true,
            message: 'Password reset successful',
        });
    } catch (error) {
        next(error);
    }
};

export {
    register,
    login,
    profile,
    googleLogin,
    forgotPassword,
    resetPassword,
};