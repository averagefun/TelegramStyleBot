from PIL import Image

# local modules
from options.test_options import TestOptions
from data import create_dataset
from models import create_model
from util.visualizer import save_images


def get_model(opt):
    model = create_model(opt) 
    model.setup(opt)
    model.eval()
    return model

if __name__ == '__main__':
    opt = TestOptions().parse()  # get test options
    opt.display_id = -1
    model = get_model(opt)

    # set aspect ratio and width of img
    img = Image.open('mydataset/image.jpg')
    w,h = img.size
    opt.aspect_ratio = h / w
    

    # create dataset
    dataset = create_dataset(opt)

    for data in dataset:
        model.set_input(data)  # unpack data from data loader
        model.test()           # run inference
        visuals = model.get_current_visuals()  # get image result
        img_path = model.get_image_paths()     # get image path
        save_images(visuals, img_path, aspect_ratio = opt.aspect_ratio)
        break
        
    # удаляем начальную картинку
    os.remove(img_path)