// Entry for the vendored three.js build (docs/design/IMMERSIVE.md 14.3, docs/design/GOLD-CARD-3D.md section 5).
// Re-exports only what the Gold Card module uses, so esbuild can tree-shake the rest.
// Build: see common/static/common/vendor/three/VERSION
export {
  WebGLRenderer, Scene, PerspectiveCamera, Group, Mesh,
  BoxGeometry, PlaneGeometry, ExtrudeGeometry, ShapeGeometry, Shape,
  MeshPhysicalMaterial, MeshBasicMaterial,
  DirectionalLight, PMREMGenerator,
  Color, Vector2, Vector3, Euler,
  CanvasTexture, Texture,
  BackSide, NeutralToneMapping, SRGBColorSpace, NoColorSpace, LinearFilter, LinearMipmapLinearFilter, ClampToEdgeWrapping, RepeatWrapping,
  MathUtils,
} from 'three';
