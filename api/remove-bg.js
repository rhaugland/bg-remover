import { removeBackground } from '@imgly/background-removal-node';

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb',
    },
  },
  maxDuration: 60,
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { image } = req.body;
    if (!image) {
      return res.status(400).json({ error: 'No image provided' });
    }

    // image is a base64 data URL
    const base64Data = image.replace(/^data:image\/\w+;base64,/, '');
    const buffer = Buffer.from(base64Data, 'base64');
    const blob = new Blob([buffer], { type: 'image/jpeg' });

    const resultBlob = await removeBackground(blob, {
      model: 'small',
    });

    const arrayBuffer = await resultBlob.arrayBuffer();
    const resultBase64 = Buffer.from(arrayBuffer).toString('base64');

    res.status(200).json({
      image: `data:image/png;base64,${resultBase64}`,
    });
  } catch (err) {
    console.error('Background removal failed:', err);
    res.status(500).json({ error: 'Failed to remove background', details: err.message });
  }
}
