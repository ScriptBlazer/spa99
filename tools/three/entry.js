// Entry for the vendored three.js build (docs/design/IMMERSIVE.md 14.3, GOLD-CARD-3D.md section 5, VIRTUAL-TOUR.md 4.2).
// Re-exports only what the Gold Card module and the virtual tour use, so esbuild can tree-shake the rest.
// Build: see common/static/common/vendor/three/VERSION
export {
  WebGLRenderer, Scene, PerspectiveCamera, Group, Mesh, Object3D, InstancedMesh,
  BufferGeometry, BufferAttribute, Float32BufferAttribute, InstancedBufferAttribute, DynamicDrawUsage,
  BoxGeometry, PlaneGeometry, ExtrudeGeometry, ShapeGeometry, Shape, Path,
  CylinderGeometry, CircleGeometry, TorusGeometry, RingGeometry, SphereGeometry,
  MeshPhysicalMaterial, MeshStandardMaterial, MeshBasicMaterial, ShaderMaterial,
  DirectionalLight, PointLight, HemisphereLight, PMREMGenerator, FogExp2,
  Color, Vector2, Vector3, Euler, Quaternion, Matrix4,
  CanvasTexture, Texture,
  BackSide, FrontSide, DoubleSide, AdditiveBlending, NormalBlending,
  NeutralToneMapping, SRGBColorSpace, NoColorSpace, LinearFilter, LinearMipmapLinearFilter, ClampToEdgeWrapping, RepeatWrapping,
  MathUtils,
} from 'three';
export { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
