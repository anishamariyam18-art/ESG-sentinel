export const validateUser = (
  req,
  res,
  next
) => {

  const {
    name,
    email
  } = req.body;

  if (!name || !email) {
    return res.status(400).json({
      success: false,
      message:
        "Invalid User Data"
    });
  }

  next();
};