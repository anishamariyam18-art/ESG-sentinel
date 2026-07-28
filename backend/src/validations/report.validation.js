import path from 'path';

const validateReportUpload = (req, res, next) => {
    const errors = [];

    if (!req.file) {
        errors.push({
            field: 'file',
            message: 'A PDF file is required',
        });
    } else {
        const extension = path.extname(req.file.originalname).toLowerCase();

        if (req.file.mimetype !== 'application/pdf' || extension !== '.pdf') {
            errors.push({
                field: 'file',
                message: 'Only PDF files are allowed',
            });
        }
    }

    if (errors.length > 0) {
        return res.status(422).json({
            success: false,
            message: 'Validation failed',
            errors,
        });
    }

    next();
};

export { validateReportUpload };