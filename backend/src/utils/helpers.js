export const generateFileName = (originalName) => {
  return `${Date.now()}-${originalName}`;
};

export const formatDate = (date) => {
  return new Date(date).toISOString();
};

export const calculateAverage = (scores) => {
  if (!scores.length) return 0;

  const total = scores.reduce(
    (sum, score) => sum + score,
    0
  );

  return total / scores.length;
};