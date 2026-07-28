import {
  createClaim,
  getAllClaims
} from "../services/claim.js";

export const extractClaim = async (req, res) => {

  try {

    const {
      claimText,
      category,
      reportId
    } = req.body;

    const claim = await createClaim({
      claimText,
      category,
      reportId
    });

    res.status(201).json({
      success: true,
      data: claim
    });

  } catch (error) {

    console.error(error);

    res.status(500).json({
      success: false,
      message: error.message
    });

  }
};

export const fetchClaims = async (req, res) => {

  try {

    const claims = await getAllClaims();

    res.status(200).json({
      success: true,
      data: claims
    });

  } catch (error) {

    res.status(500).json({
      success: false,
      message: error.message
    });

  }
};