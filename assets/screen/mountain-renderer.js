// The transparent scene contains only the installations. Their foot positions
// and apparent heights are supplied in photo coordinates by mountain-scene.
export function buildFarmRenderer(THREE, canvas, context) {
  const renderer = new THREE.WebGLRenderer({canvas, context, alpha: true, antialias: true});
  renderer.setClearColor(0, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(0, 1, 0, -1, .1, 12000);
  camera.position.z = 6000;

  const sunlight = new THREE.DirectionalLight(0xfff6df, 2.25);
  sunlight.position.set(-60, 85, 45);
  scene.add(sunlight, new THREE.HemisphereLight(0xeaf5fc, 0x808977, 1.55));
  const painted = new THREE.MeshStandardMaterial({color: 0xd9ddd6, roughness: .57, metalness: .16});
  const tipPaint = new THREE.MeshStandardMaterial({color: 0x7b8486, roughness: .7});
  const concrete = new THREE.MeshStandardMaterial({color: 0xa2a597, roughness: .94});
  const hatch = new THREE.MeshStandardMaterial({color: 0x636e70, roughness: .77});
  const fault = new THREE.MeshStandardMaterial({
    color: 0xce0b27, roughness: .69, emissive: 0xff1731, emissiveIntensity: .48,
  });
  const clear = new THREE.MeshStandardMaterial({
    color: 0x0964d1, roughness: .65, emissive: 0x0572fa, emissiveIntensity: .55,
  });
  const statusMaterials = {damaged: fault, clear};

  // Elliptical, swept airfoil sections get narrower and untwist towards the tip.
  const profiles = [
    [0, 0, .46, .43], [2, 0, .61, .52], [4.8, -.12, 1.2, .55], [8.2, -.35, 1.48, .46],
    [14, -.42, 1.36, .38], [22, -.30, .95, .25], [28.7, -.14, .63, .18],
    [30.5, -.03, .51, .14], [32.3, .06, .4, .10], [34.5, .20, .25, .07], [36.8, .41, .065, .03],
  ];
  const bladeGeometry = new THREE.BufferGeometry();
  const vertices = [], indices = [];
  const sides = 12;
  profiles.forEach(([y, sweep, chord, thickness], ring) => {
    const twist = .29 * (1 - y / 37) - .09;
    const firstIndex = indices.length;
    for (let side = 0; side < sides; side++) {
      const angle = side * Math.PI * 2 / sides;
      const x = chord * Math.cos(angle), z = thickness * Math.sin(angle);
      vertices.push(sweep + x * Math.cos(twist) - z * Math.sin(twist), y,
        z * Math.cos(twist) + x * Math.sin(twist));
      if (ring === 0) continue;
      const lower = (ring - 1) * sides, upper = ring * sides, next = (side + 1) % sides;
      indices.push(lower + side, upper + side, upper + next, lower + side, upper + next, lower + next);
    }
    if (ring > 0) bladeGeometry.addGroup(firstIndex, indices.length - firstIndex, ring === 8 || ring === 10 ? 1 : 0);
  });
  bladeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  bladeGeometry.setIndex(indices);
  bladeGeometry.computeVertexNormals();

  const geometry = {
    tower: new THREE.CylinderGeometry(.84, 1.36, 64, 32),
    foundation: new THREE.CylinderGeometry(2.15, 2.6, .65, 32),
    nacelle: new THREE.SphereGeometry(1, 28, 18),
    hub: new THREE.SphereGeometry(1.4, 24, 18),
    door: new THREE.BoxGeometry(.72, 1.72, .17),
    vent: new THREE.BoxGeometry(1.25, .18, 2.05),
  };
  const models = new Map();
  const pickable = [];
  let findings = new Map();

  function createTurbine(id) {
    const group = new THREE.Group();
    // Slightly above and across the rotor, with the hub facing the sunlit valley.
    group.rotation.set(.12, .62, 0);
    scene.add(group);
    const meshes = [];
    function part(parent, name, shape, material, x, y, z) {
      const mesh = new THREE.Mesh(shape, material);
      mesh.position.set(x, y, z);
      mesh.userData = {unit: id, part: name, material};
      meshes.push(mesh);
      pickable.push(mesh);
      parent.add(mesh);
      return mesh;
    }
    part(group, 'foundation', geometry.foundation, concrete, 0, .325, 0);
    part(group, 'tower', geometry.tower, painted, 0, 32.32, 0);
    part(group, 'tower', geometry.door, hatch, -.33, 1.35, 1.29);
    const nacelle = part(group, 'nacelle', geometry.nacelle, painted, 0, 64.6, -1.5);
    nacelle.scale.set(1.45, 1.3, 4.3);
    part(group, 'nacelle', geometry.vent, hatch, 0, 65.83, -1.75);
    const rotor = new THREE.Group();
    rotor.position.set(0, 64.6, 2);
    group.add(rotor);
    part(rotor, 'hub', geometry.hub, painted, 0, 0, .26).scale.z = 1.65;
    const bladeMaterials = [painted, tipPaint];
    for (let i = 0; i < 3; i++) {
      part(rotor, 'blade', bladeGeometry, bladeMaterials, 0, 0, 0).rotation.z = i * 2 * Math.PI / 3;
    }
    // Phase is tied to a unit, independent of which units are in the frame.
    const phase = (Number(id.slice(2)) - 3) * .78;
    const model = {group, rotor, meshes, phase};
    models.set(id, model);
    applyFindings(id, model);
    return model;
  }
  function applyFindings(id, model) {
    const parts = findings.get(id);
    for (const mesh of model.meshes) {
      mesh.material = statusMaterials[parts?.get(mesh.userData.part)] || mesh.userData.material;
    }
  }

  let width = 0, height = 0;
  const pointer = new THREE.Vector2(), ray = new THREE.Raycaster();
  return {
    frame(frame) {
      if (width !== frame.width || height !== frame.height) {
        width = frame.width;
        height = frame.height;
        renderer.setSize(width, height, false);
        camera.right = width;
        camera.bottom = -height;
        camera.updateProjectionMatrix();
        camera.updateMatrixWorld();
      }
      for (const model of models.values()) model.group.visible = false;
      frame.placements.forEach((placement, index) => {
        const model = models.get(placement.id) || createTurbine(placement.id);
        const scale = placement.height / 101;
        // Layers arrive back to front. Give each installation its own depth slab.
        model.group.position.set(placement.x, -placement.y, index * 400);
        model.group.scale.setScalar(scale);
        model.group.visible = placement.visible;
        model.group.updateMatrixWorld(true);
      });
    },
    mark(units) {
      findings = units;
      for (const [id, model] of models) applyFindings(id, model);
    },
    draw(angle) {
      for (const {rotor, phase} of models.values()) rotor.rotation.z = angle + phase;
      renderer.render(scene, camera);
    },
    pick(x, y) {
      if (!width || !height) return;
      pointer.set(x / width * 2 - 1, 1 - y / height * 2);
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(pickable, false).find(({object}) =>
        models.get(object.userData.unit).group.visible);
      return hit?.object.userData.unit;
    },
  };
}
