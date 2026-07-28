import prisma from "../config/prisma.js";

export const verifyClaim = async (req, res) => {

  try {

    const {
      claimId,
      verificationStatus,
      confidence,
      reason
    } = req.body;

    const result = await prisma.verification.create({
      data: {
        claimId,
        verificationStatus,
        confidence,
        reason
      }
    });

    res.status(201).json({
      success: true,
      data: result
    });

  } catch (error) {

    res.status(500).json({
      success: false,
      message: error.message
    });

  }
};